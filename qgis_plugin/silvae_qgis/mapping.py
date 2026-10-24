"""Corrispondenza colonna del layer → campo Silvae, ricordata nel progetto.

Si decide una volta per layer: la scelta sta nelle proprietà del progetto
QGIS (`silvae/mapping/<id layer>`), quindi riaprendo il progetto l'invio non
richiede di rifarla. La proposta iniziale arriva dal server (stessa
auto-mappatura dell'import da file), così la logica di riconoscimento dei
nomi di colonna vive in un posto solo.
"""
import json

from qgis.core import QgsProject

SCOPE = 'silvae'
# Colonne scritte dal plugin nel layer dell'agronomo: `silvae_uuid` è la
# chiave di collegamento, le altre due sono solo informative.
LINK_COLUMN_FIELDS = {'silvae_uuid': 'uuid', 'silvae_id': '', 'silvae_synced_at': ''}


def _key(layer):
    return f'mapping/{layer.id()}'


def load(project, layer):
    """Mappatura salvata per il layer, o None se non è mai stata decisa."""
    raw, ok = project.readEntry(SCOPE, _key(layer), '')
    if not ok or not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def save(project, layer, mapping):
    project.writeEntry(SCOPE, _key(layer), json.dumps(mapping, ensure_ascii=False))


def forget(project, layer):
    project.removeEntry(SCOPE, _key(layer))


def suggest(client, layer, project=None):
    """Mappatura da proporre nella finestra: quella salvata se c'è, altrimenti
    quella proposta dal server, con le colonne scritte dal plugin già al
    posto giusto. Ritorna (mapping, campi_disponibili)."""
    columns = [f.name() for f in layer.fields()]
    suggested = client.suggest_mapping(columns)
    fields = suggested.get('fields') or []
    mapping = load(project or QgsProject.instance(), layer)
    if mapping is None:
        mapping = dict(suggested.get('mapping') or {})
    # Colonne sparite dal layer o campi non più validi: si scartano.
    mapping = {c: f for c, f in mapping.items() if c in columns and (f in fields or f == '')}
    # Le colonne scritte dal plugin hanno un significato fisso: si aggiungono
    # anche a una mappatura salvata prima che esistessero (le scrive il primo
    # invio), a meno che l'utente non le abbia già decise.
    for col, field in LINK_COLUMN_FIELDS.items():
        if col in columns and col not in mapping:
            mapping[col] = field
    return mapping, fields
