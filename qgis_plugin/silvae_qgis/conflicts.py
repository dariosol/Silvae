"""Risoluzione dei conflitti di un invio a Silvae.

Un conflitto significa che quell'albero è cambiato sul server dopo l'ultimo
scaricamento: il push non l'ha scritto (qgis.md §6.2). Qui si mette a
confronto ciò che ha QGIS con ciò che ha Silvae, campo per campo, e si
sceglie per ognuno:

  mine    la versione di QGIS vince → reinvio con `force`
  server  vince Silvae → i valori del server vengono scritti nel layer locale
  skip    non si fa nulla; l'albero resterà in conflitto al prossimo invio
"""
from qgis.PyQt.QtCore import QVariant

from . import push as push_mod

MINE, SERVER, SKIP = 'mine', 'server', 'skip'

# Campi che cambiano da sé (li calcola o li tiene il server): non si mostrano
# come differenze da decidere.
_NOISE = {'updated_at', 'updated_by', 'rischio_json', 'rischio_classe', 'rischio_label',
          'rischio_rami', 'rischio_tronco', 'rischio_colletto', 'rischio_zolla',
          'rischio_residuo_classe', 'stat_bucket', 'stat_label', 'cond_classe',
          'cond_label', 'bio_kg', 'co2_kg_anno', 'o2_kg_anno', 'ia_kg_anno',
          'valore_ecologico', 'bersaglio_chioma', 'bersaglio_ramo', 'owner', 'id'}


def _same(a, b):
    """Confronto indulgente: '' e None sono la stessa cosa, i numeri si
    confrontano come numeri (QGIS restituisce spesso stringhe)."""
    if a in (None, '') and b in (None, ''):
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            pass
    return str(a).strip() == str(b).strip()


def describe(client, layer, conflicts, mapping):
    """Per ogni conflitto: valori locali e del server sui campi mappati, e
    l'elenco di quelli che differiscono davvero.

    Ritorna una lista di dict con `entry` (la voce del push), `fid`,
    `custom_id`, `diffs` = [(campo, valore_qgis, valore_silvae)]."""
    ids = [c['id'] for c in conflicts if c.get('id')]
    if not ids:
        return []
    fc = client.features(ids=ids)
    by_id = {f['id']: f.get('properties', {}) for f in fc.get('features', [])}
    # campo Silvae → colonna del layer (per leggere i valori locali)
    col_of = {}
    for col, field in (mapping or {}).items():
        if field and field not in col_of.values():
            col_of[field] = col
    if not col_of:
        col_of = {f.name(): f.name() for f in layer.fields()}

    out = []
    names = {f.name() for f in layer.fields()}
    for c in conflicts:
        props = by_id.get(c.get('id'))
        if props is None:
            continue
        feat = next(layer.getFeatures(f'$id = {c["fid"]}'), None) if c.get('fid') is not None else None
        diffs = []
        for field, server_val in props.items():
            if field in _NOISE:
                continue
            col = col_of.get(field)
            if not col or col not in names or feat is None:
                continue
            local_val = push_mod._json_value(feat[col])
            if not _same(local_val, server_val):
                diffs.append((field, local_val, server_val))
        out.append({'entry': c, 'fid': c.get('fid'), 'id': c.get('id'),
                    'custom_id': c.get('custom_id') or (props.get('custom_id') or ''),
                    'server_updated_by': c.get('server_updated_by'),
                    'server_updated_at': c.get('server_updated_at'),
                    'server_props': props, 'diffs': sorted(diffs)})
    return out


def apply_server_values(layer, rows, mapping):
    """Scrive nel layer i valori del server per i conflitti risolti con
    `server`. Ritorna il numero di feature aggiornate."""
    if not rows:
        return 0
    fields = layer.fields()
    updated = 0
    if not layer.startEditing():
        return 0
    try:
        for row in rows:
            fid = row.get('fid')
            if fid is None:
                continue
            props = row['server_props']
            for col, field in (mapping or {}).items():
                idx = fields.indexOf(col)
                if idx < 0 or not field or field not in props:
                    continue
                v = props[field]
                layer.changeAttributeValue(fid, idx, v if v is not None else QVariant())
            geom = None
            lat, lon = props.get('latitude'), props.get('longitude')
            if lat is not None and lon is not None:
                from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                                       QgsGeometry, QgsPointXY, QgsProject)
                pt = QgsPointXY(float(lon), float(lat))
                if layer.crs().authid() != 'EPSG:4326':
                    tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),
                                                layer.crs(), QgsProject.instance())
                    pt = tr.transform(pt)
                geom = QgsGeometry.fromPointXY(pt)
            if geom is not None:
                layer.changeGeometry(fid, geom)
            updated += 1
        if not layer.commitChanges():
            raise RuntimeError('; '.join(layer.commitErrors()))
    except Exception:
        layer.rollBack()
        raise
    return updated


def resolve(client, layer, rows, choices, city, mapping, on_conflict='update'):
    """Applica le scelte. `choices` è {fid: MINE|SERVER|SKIP}.

    Ritorna {'forced': risultato del push con force, 'from_server': n, 'skipped': n}.
    Le feature risolte (in un senso o nell'altro) vengono ri-timbrate con
    `silvae_synced_at`, così non tornano in conflitto al prossimo invio."""
    mine = [r for r in rows if choices.get(r['fid']) == MINE and r['fid'] is not None]
    server = [r for r in rows if choices.get(r['fid']) == SERVER and r['fid'] is not None]
    skipped = [r for r in rows if choices.get(r['fid'], SKIP) == SKIP]

    forced = None
    if mine:
        forced = push_mod.push(client, layer, city, mapping=mapping,
                               on_conflict=on_conflict, force=True,
                               limit_ids={r['fid'] for r in mine})
        push_mod.write_back_links(layer, forced)

    n_server = apply_server_values(layer, server, mapping)
    if server:
        fake = {'updated': [{'fid': r['fid'], 'uuid': r['server_props'].get('uuid'),
                             'id': r['id']} for r in server]}
        push_mod.write_back_links(layer, fake)
    return {'forced': forced, 'from_server': n_server, 'skipped': len(skipped)}
