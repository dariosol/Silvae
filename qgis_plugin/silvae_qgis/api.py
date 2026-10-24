"""Client HTTP verso Silvae Pro.

Usa QgsBlockingNetworkRequest (sincrono, rispetta proxy e certificati di
QGIS) e il token API `slv_…` nell'header Authorization. Nessuna dipendenza
da `requests`, che in QGIS non è garantito.
"""
import json
from urllib.parse import urlencode

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsBlockingNetworkRequest

USER_AGENT = b'SilvaePro-QGIS/0.1'


class SilvaeError(Exception):
    """Errore di rete o risposta non 2xx; `status` è il codice HTTP (0 se rete)."""

    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


class SilvaeClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token

    # --- trasporto ---------------------------------------------------------
    def _request(self, path, params=None, auth=True, method='GET', payload=None):
        url = self.base_url + path
        if params:
            url += '?' + urlencode({k: v for k, v in params.items() if v not in (None, '')})
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b'User-Agent', USER_AGENT)
        # Mai la cache di QGIS: stesso URL con token diverso = risposta diversa.
        req.setAttribute(QNetworkRequest.CacheLoadControlAttribute, QNetworkRequest.AlwaysNetwork)
        req.setAttribute(QNetworkRequest.CacheSaveControlAttribute, False)
        if auth and self.token:
            req.setRawHeader(b'Authorization', f'Bearer {self.token}'.encode())
        if payload is not None:
            req.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        blocking = QgsBlockingNetworkRequest()
        if method == 'POST':
            err = blocking.post(req, json.dumps(payload).encode('utf-8'))
        elif method == 'DELETE':
            err = blocking.deleteResource(req)
        else:
            err = blocking.get(req)
        reply = blocking.reply()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
        body = bytes(reply.content())
        if err != QgsBlockingNetworkRequest.NoError and not status:
            raise SilvaeError(f'Errore di rete: {blocking.errorMessage()}', 0)
        if status >= 400:
            msg = ''
            try:
                msg = json.loads(body.decode('utf-8')).get('message', '')
            except Exception:
                pass
            if status == 401:
                msg = msg or 'Token non valido o revocato'
            raise SilvaeError(msg or f'HTTP {status}', status)
        return status, body

    def get_json(self, path, params=None, auth=True):
        _status, body = self._request(path, params, auth)
        return json.loads(body.decode('utf-8'))

    def post_json(self, path, payload):
        _status, body = self._request(path, method='POST', payload=payload)
        return json.loads(body.decode('utf-8'))

    # --- endpoint ----------------------------------------------------------
    def me(self):
        return self.get_json('/me')

    def cities(self):
        return self.get_json('/cities')

    def features(self, city=None, ids=None, since=None, bbox=None):
        """FeatureCollection (dict) di GET /qgis/features."""
        params = {'city': city, 'since': since, 'bbox': bbox}
        if ids:
            params['ids'] = ','.join(str(i) for i in ids)
        return self.get_json('/qgis/features', params)

    def deliveries(self, include_fetched=False):
        """Invii in attesa per l'utente del token (GET /qgis/deliveries)."""
        return self.get_json('/qgis/deliveries', {'all': '1' if include_fetched else None})

    def delivery_features(self, delivery_id):
        """Ritira un invio: FeatureCollection con gli alberi correnti e, in
        `silvae.delivery`, i dati dell'invio (compreso il perimetro)."""
        return self.get_json('/qgis/features', {'delivery': delivery_id})

    def delete_delivery(self, delivery_id):
        self._request(f'/qgis/deliveries/{delivery_id}', method='DELETE')

    def suggest_mapping(self, columns):
        """Mappatura proposta e campi scrivibili per le colonne di un layer
        (POST /qgis/mapping): la stessa auto-mappatura dell'import da file."""
        return self.post_json('/qgis/mapping', {'columns': list(columns)})

    def push_features(self, features, city, mapping=None, on_conflict='update',
                      dry_run=False, force=False):
        """Invia feature GeoJSON a Silvae (POST /qgis/features). Con
        `dry_run` il server non scrive e risponde con l'anteprima del diff."""
        return self.post_json('/qgis/features', {
            'type': 'FeatureCollection', 'features': features, 'city': city,
            'mapping': mapping or {}, 'on_conflict': on_conflict,
            'dry_run': bool(dry_run), 'force': bool(force)})

    def style_qml(self, by='stat', field=None, labels=True):
        """Testo del .qml di GET /qgis/style.qml (endpoint pubblico)."""
        _status, body = self._request('/qgis/style.qml',
                                      {'by': by, 'field': field, 'labels': '1' if labels else '0'},
                                      auth=False)
        return body.decode('utf-8')
