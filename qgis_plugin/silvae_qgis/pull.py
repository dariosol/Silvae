"""«Carica da Silvae»: scarica gli alberi di un comune nel GPKG locale.

Prima volta: crea il file, aggiunge il layer al progetto e applica lo stile.
Volte successive (file già nel progetto): pull incrementale con `since=`
(data dell'ultimo pull salvata nel progetto) e aggiornamento per uuid.
"""
import os

from . import layer_store

PROJECT_SCOPE = 'silvae'


def _entry_key(city):
    return f'last_pull/{city}'


def last_pull(project, city):
    val, ok = project.readEntry(PROJECT_SCOPE, _entry_key(city), '')
    return val if ok and val else None


def _save_pull(project, city, generated_at):
    project.writeEntry(PROJECT_SCOPE, _entry_key(city), generated_at)


def pull_delivery(client, project, delivery, directory, style_by='stat'):
    """Ritira un invio della cassetta postale: aggiorna (o crea) il GPKG del
    comune dell'invio con quegli alberi, e disegna il perimetro dell'area se
    c'è. Ritorna lo stesso dict di pull_city, più 'polygon_layer'."""
    fc = client.delivery_features(delivery['id'])
    feats = fc.get('features', [])
    info = fc.get('silvae') or {}
    city = delivery.get('city') or info.get('city') or 'invio'

    path = layer_store.gpkg_path_for(city, directory)
    layer = layer_store.find_project_layer(project, path)
    if layer is not None and os.path.exists(path):
        added, updated = layer_store.upsert_features(layer, feats)
        result = {'mode': 'updated', 'added': added, 'updated': updated}
    else:
        layer_store.create_gpkg(feats, path)
        layer = layer_store.open_layer(path, f'Silvae — {city}')
        project.addMapLayer(layer)
        result = {'mode': 'created', 'added': len(feats), 'updated': 0}
        try:
            layer_store.apply_style(layer, client.style_qml(style_by))
        except Exception as e:
            result['style_error'] = str(e)

    polygon = delivery.get('polygon')
    result['polygon_layer'] = (layer_store.add_polygon_layer(project, polygon, f'Area — {delivery["title"]}')
                               if polygon else None)
    result.update({'layer': layer, 'path': path, 'count': layer.featureCount(),
                   'generated_at': info.get('generated_at'), 'city': city,
                   'received': len(feats)})
    return result


def pull_city(client, project, city, directory, style_by='stat', force_full=False):
    """Ritorna dict {'layer', 'path', 'mode': 'created'|'updated', 'count',
    'added', 'updated', 'generated_at'}."""
    path = layer_store.gpkg_path_for(city, directory)
    layer = layer_store.find_project_layer(project, path)
    incremental = layer is not None and os.path.exists(path) and not force_full

    since = last_pull(project, city) if incremental else None
    fc = client.features(city=city, since=since)
    feats = fc.get('features', [])
    generated_at = (fc.get('silvae') or {}).get('generated_at')

    if incremental:
        added, updated = layer_store.upsert_features(layer, feats)
        result = {'mode': 'updated', 'added': added, 'updated': updated}
    else:
        if layer is not None:
            project.removeMapLayer(layer.id())
        layer_store.create_gpkg(feats, path)
        layer = layer_store.open_layer(path, f'Silvae — {city}')
        project.addMapLayer(layer)
        result = {'mode': 'created', 'added': len(feats), 'updated': 0}
        try:
            layer_store.apply_style(layer, client.style_qml(style_by))
        except Exception as e:   # lo stile è un comfort, non blocca il caricamento
            result['style_error'] = str(e)

    if generated_at:
        _save_pull(project, city, generated_at)
    result.update({'layer': layer, 'path': path, 'count': layer.featureCount(),
                   'generated_at': generated_at})
    return result
