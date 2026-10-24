"""GeoPackage locale con gli alberi di un comune.

Il file sta nella cartella del progetto (`silvae_<comune>.gpkg`, layer
`alberi`): sopravvive alla chiusura, funziona offline e si apre in QField.
Prima creazione dal GeoJSON del server; poi aggiornamenti incrementali per
`uuid` (feature nuove aggiunte, esistenti aggiornate; quelle sparite dal
server restano — nessuna cancellazione automatica, docs/qgis.md §13).
"""
import json
import os
import re
import tempfile

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsField,
                       QgsFields, QgsGeometry, QgsPointXY, QgsProject,
                       QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes,
                       QgsCoordinateReferenceSystem)

LAYER_NAME = 'alberi'
KEY_FIELD = 'uuid'
# Campi numerici del GeoJSON di Silvae: tutto il resto è testo. Tipizzarli a
# mano evita che OGR indovini (una colonna tutta vuota diventerebbe testo).
INT_FIELDS = {'id', 'bersaglio_chioma', 'bersaglio_ramo', 'moltiplicatore'}
REAL_FIELDS = {'latitude', 'longitude', 'trunk_diameter_cm', 'crown_diameter_m',
               'tree_height_m', 'circonferenza_cm', 'branch_diam_cm', 'branch_length_m',
               'branch_height_m', 'target_height_m', 'post_tree_height_m',
               'post_circonferenza_cm', 'post_branch_diam_cm', 'post_branch_length_m',
               'post_branch_height_m', 'post_target_height_m', 'bersaglio_chioma_flow',
               'bersaglio_ramo_flow', 'bio_kg', 'co2_kg_anno', 'o2_kg_anno',
               'ia_kg_anno', 'valore_ecologico'}


def gpkg_path_for(city, directory):
    slug = re.sub(r'[^a-z0-9]+', '_', city.lower()).strip('_') or 'comune'
    return os.path.join(directory, f'silvae_{slug}.gpkg')


def fields_from_features(features):
    """QgsFields con l'unione delle proprietà, nell'ordine della prima feature."""
    names = []
    for f in features:
        for k in f.get('properties', {}):
            if k not in names:
                names.append(k)
    fields = QgsFields()
    for n in names:
        if n in INT_FIELDS:
            fields.append(QgsField(n, QVariant.LongLong))
        elif n in REAL_FIELDS:
            fields.append(QgsField(n, QVariant.Double))
        else:
            fields.append(QgsField(n, QVariant.String))
    return fields


def _value(name, v):
    if v is None or v == '':
        return None if (name in INT_FIELDS or name in REAL_FIELDS) else v
    if name in INT_FIELDS:
        return int(v)
    if name in REAL_FIELDS:
        return float(v)
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def to_qgs_feature(gj, fields):
    """Feature GeoJSON (dict) → QgsFeature con i campi `fields`."""
    f = QgsFeature(fields)
    props = gj.get('properties', {})
    for i, fld in enumerate(fields):
        f.setAttribute(i, _value(fld.name(), props.get(fld.name())))
    geom = gj.get('geometry')
    if geom and geom.get('type') == 'Point':
        lon, lat = geom['coordinates'][:2]
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
    return f


def create_gpkg(features, path):
    """Scrive un nuovo GPKG con `features` (GeoJSON) nel layer `alberi`.
    Ritorna il percorso. Sovrascrive un file esistente."""
    fields = fields_from_features(features)
    crs = QgsCoordinateReferenceSystem('EPSG:4326')
    if os.path.exists(path):
        os.remove(path)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = 'GPKG'
    opts.layerName = LAYER_NAME
    opts.fileEncoding = 'UTF-8'
    writer = QgsVectorFileWriter.create(path, fields, QgsWkbTypes.Point, crs,
                                        QgsCoordinateTransformContext(), opts)
    if writer.hasError() != QgsVectorFileWriter.NoError:
        raise RuntimeError(f'Impossibile creare {path}: {writer.errorMessage()}')
    for gj in features:
        writer.addFeature(to_qgs_feature(gj, fields))
    del writer
    return path


def open_layer(path, name=None):
    lyr = QgsVectorLayer(f'{path}|layername={LAYER_NAME}', name or LAYER_NAME, 'ogr')
    if not lyr.isValid():
        raise RuntimeError(f'GPKG non valido o senza layer {LAYER_NAME}: {path}')
    return lyr


def upsert_features(layer, features):
    """Aggiorna il layer con `features` (GeoJSON) per uuid: (aggiunte, aggiornate)."""
    fields = layer.fields()
    key_idx = fields.indexOf(KEY_FIELD)
    if key_idx < 0:
        raise RuntimeError(f'Il layer non ha il campo {KEY_FIELD}')
    by_key = {}
    for f in layer.getFeatures():
        by_key[f[KEY_FIELD]] = f.id()
    # La chiave primaria del GPKG (fid) la assegna il provider: non si tocca.
    pk = set(layer.primaryKeyAttributes())
    writable = [i for i in range(fields.count()) if i not in pk]
    added = updated = 0
    if not layer.startEditing():
        raise RuntimeError('Il layer non è modificabile')
    try:
        for gj in features:
            nf = to_qgs_feature(gj, fields)
            key = gj.get('properties', {}).get(KEY_FIELD)
            fid = by_key.get(key)
            if fid is None:
                layer.addFeature(nf)
                added += 1
            else:
                for i in writable:
                    layer.changeAttributeValue(fid, i, nf.attribute(i))
                layer.changeGeometry(fid, nf.geometry())
                updated += 1
        if not layer.commitChanges():
            raise RuntimeError('; '.join(layer.commitErrors()))
    except Exception:
        layer.rollBack()
        raise
    return added, updated


def apply_style(layer, qml_text):
    """Applica un .qml (testo) al layer."""
    doc = QDomDocument()
    ok, err, _line, _col = doc.setContent(qml_text)
    if not ok:
        raise RuntimeError(f'Stile non valido: {err}')
    applied, msg = layer.importNamedStyle(doc)
    if not applied:
        raise RuntimeError(f'Stile non applicato: {msg}')
    layer.triggerRepaint()


def add_polygon_layer(project, polygon, name):
    """Layer temporaneo (in memoria) col perimetro dell'area di un invio:
    è un riferimento visivo, non un dato da conservare."""
    if not polygon or len(polygon) < 3:
        return None
    lyr = QgsVectorLayer('Polygon?crs=EPSG:4326', name, 'memory')
    ring = [QgsPointXY(float(lon), float(lat)) for lat, lon in polygon]
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromPolygonXY([ring]))
    lyr.dataProvider().addFeature(f)
    lyr.updateExtents()
    renderer = lyr.renderer()
    if renderer is not None:
        sym = renderer.symbol()
        sym.setColor(QColor(88, 150, 50, 40))
        if sym.symbolLayerCount():
            sl = sym.symbolLayer(0)
            sl.setStrokeColor(QColor('#589632'))
            sl.setStrokeWidth(0.6)
    project.addMapLayer(lyr)
    return lyr


def find_project_layer(project, path):
    """Layer del progetto che punta a `path` (GPKG), o None."""
    norm = os.path.normcase(os.path.abspath(path))
    for lyr in project.mapLayers().values():
        src = lyr.source().split('|')[0]
        if os.path.normcase(os.path.abspath(src)) == norm:
            return lyr
    return None
