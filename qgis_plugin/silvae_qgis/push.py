"""«Invia a Silvae»: dalle feature di un layer QGIS al server.

Il layer può essere qualsiasi cosa (shapefile, GPKG, memoria, PostGIS) e
avere colonne proprie: la corrispondenza colonna → campo Silvae si decide
una volta e resta salvata nel progetto (`mapping.py`).

Regole (docs/qgis.md §6.2), applicate dal server e riflesse qui:
  - la geometria viene riproiettata in EPSG:4326 e vince sulle colonne
    latitude/longitude, che in un layer scaricato restano quelle del pull;
  - `uuid` è la chiave: al primo invio il server lo assegna e il plugin lo
    scrive nel layer (`silvae_uuid`), così gli invii successivi aggiornano
    invece di duplicare;
  - `updated_at` viaggia con la feature: se il server è più avanti la feature
    finisce in `conflicts` e non viene scritta.
"""
from datetime import datetime, timezone

from qgis.PyQt.QtCore import QDateTime, QVariant
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsField, QgsProject)

WGS84 = 'EPSG:4326'
# Campi scritti nel layer dopo un invio riuscito. Su un layer scaricato da
# Silvae le colonne `uuid` e `id` ci sono già e sono quelle giuste: si
# riempiono quelle (un albero disegnato a mano nel GPKG non ha uuid finché
# non lo assegna il server), e non si aggiungono doppioni `silvae_*`.
LINK_FIELDS = [('silvae_uuid', QVariant.String), ('silvae_id', QVariant.LongLong),
               ('silvae_synced_at', QVariant.String)]
SYNCED_FIELD = ('silvae_synced_at', QVariant.String)
CHUNK = 500


def _json_value(v):
    """Valore di attributo QGIS → valore JSON."""
    if v is None or (isinstance(v, QVariant) and v.isNull()):
        return None
    if isinstance(v, QDateTime):
        return v.toString('yyyy-MM-dd')
    if hasattr(v, 'toString'):        # QDate, QTime
        return v.toString('yyyy-MM-dd')
    return v


def features_to_geojson(layer, only_selected=False, limit_ids=None):
    """Feature del layer → lista GeoJSON in WGS84 (geometria + attributi).
    Ritorna anche la mappa indice_nella_lista → fid, per la scrittura di
    ritorno degli uuid."""
    transform = None
    if layer.crs().authid() != WGS84:
        transform = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem(WGS84),
                                           QgsProject.instance())
    names = [f.name() for f in layer.fields()]
    feats, fids = [], []
    source = layer.getSelectedFeatures() if only_selected else layer.getFeatures()
    for f in source:
        if limit_ids is not None and f.id() not in limit_ids:
            continue
        props = {n: _json_value(f[n]) for n in names}
        geom = None
        g = f.geometry()
        if g and not g.isEmpty():
            g = QgsGeometryHelper.to_wgs84(g, transform)
            pt = g.asPoint() if g.type() == 0 else g.centroid().asPoint()
            geom = {'type': 'Point', 'coordinates': [pt.x(), pt.y()]}
        feats.append({'type': 'Feature', 'geometry': geom, 'properties': props})
        fids.append(f.id())
    return feats, fids


class QgsGeometryHelper:
    """Riproiezione isolata, così `features_to_geojson` resta leggibile."""

    @staticmethod
    def to_wgs84(geom, transform):
        if transform is None:
            return geom
        g = type(geom)(geom)
        g.transform(transform)
        return g


def push(client, layer, city, mapping=None, only_selected=False, on_conflict='update',
         dry_run=False, force=False, limit_ids=None, progress=None):
    """Invia il layer a Silvae a blocchi di CHUNK feature.

    `progress(inviate, totali)` è chiamata dopo ogni blocco. Ritorna il
    risultato consolidato del server, con gli indici `src` riferiti alla
    lista completa e `fids` per risalire alle feature del layer.

    Dopo un invio **non** di prova va sempre chiamata `write_back_links`: è
    quella che aggiorna `silvae_synced_at`, cioè «fin qui ho visto». Senza,
    il prossimo invio vedrebbe come conflitto le modifiche fatte da questo."""
    feats, fids = features_to_geojson(layer, only_selected, limit_ids)
    total = len(feats)
    merged = {k: [] for k in ('created', 'updated', 'unchanged', 'skipped', 'conflicts', 'errors')}
    ignored = set()
    for start in range(0, total, CHUNK):
        block = feats[start:start + CHUNK]
        res = client.push_features(block, city, mapping=mapping, on_conflict=on_conflict,
                                   dry_run=dry_run, force=force)
        for key in merged:
            for entry in res.get(key, []):
                entry = dict(entry)
                entry['src'] = start + entry.get('src', 0)
                entry['fid'] = fids[entry['src']] if entry['src'] < len(fids) else None
                merged[key].append(entry)
        ignored.update(res.get('ignored_fields') or [])
        if progress:
            progress(min(start + CHUNK, total), total)
    merged['counts'] = {k: len(v) for k, v in merged.items()}
    merged['ignored_fields'] = sorted(ignored)
    merged['total'] = total
    merged['dry_run'] = dry_run
    return merged


def write_back_links(layer, result, when=None):
    """Scrive `silvae_uuid`/`silvae_id`/`silvae_synced_at` nelle feature
    inviate con successo: da qui in poi il layer dell'agronomo è collegato.

    `when` è una data ISO 8601 UTC (di default adesso): il server la rilegge
    al prossimo invio come «ultimo stato visto» per riconoscere i conflitti
    sui layer che non hanno la colonna `updated_at` di Silvae.
    Ritorna il numero di feature aggiornate; 0 se il layer non è modificabile."""
    when = when or datetime.now(timezone.utc).isoformat()
    caps = layer.dataProvider().capabilities()
    from qgis.core import QgsVectorDataProvider
    if not (caps & QgsVectorDataProvider.ChangeAttributeValues):
        return 0
    silvae_layer = layer.fields().indexOf('uuid') >= 0      # layer scaricato da Silvae
    needed = [SYNCED_FIELD] if silvae_layer else list(LINK_FIELDS)
    missing = [(n, t) for n, t in needed if layer.fields().indexOf(n) < 0]
    if missing:
        if not (caps & QgsVectorDataProvider.AddAttributes):
            return 0
        layer.dataProvider().addAttributes([QgsField(n, t) for n, t in missing])
        layer.updateFields()
    key_col = 'uuid' if silvae_layer else 'silvae_uuid'
    id_col  = 'id'   if silvae_layer else 'silvae_id'
    idx = {n: layer.fields().indexOf(n) for n in (key_col, id_col, 'silvae_synced_at')}
    rows = [e for key in ('created', 'updated', 'unchanged')
            for e in result.get(key, []) if e.get('fid') is not None and e.get('uuid')]
    if not rows:
        return 0
    if not layer.startEditing():
        return 0
    try:
        for e in rows:
            layer.changeAttributeValue(e['fid'], idx[key_col], e['uuid'])
            if e.get('id') is not None and idx[id_col] >= 0:
                layer.changeAttributeValue(e['fid'], idx[id_col], e['id'])
            layer.changeAttributeValue(e['fid'], idx['silvae_synced_at'], when)
        if not layer.commitChanges():
            raise RuntimeError('; '.join(layer.commitErrors()))
    except Exception:
        layer.rollBack()
        raise
    return len(rows)
