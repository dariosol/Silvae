"""Impostazioni persistenti del plugin (QgsSettings): URL del server, token
API e ultimo comune scelto.

Il token è salvato in QgsSettings (file .ini del profilo QGIS), non nel
gestore autenticazioni cifrato: scelta della fase 1 per non richiedere la
master password; il passaggio ad `APIHeader` nel gestore autenticazioni tocca
solo questo modulo (docs/qgis.md §9.2).
"""
from qgis.core import QgsSettings

GROUP = 'silvae'
DEFAULT_URL = 'https://silvae.up.railway.app'


def _s():
    return QgsSettings()


def base_url():
    return (_s().value(f'{GROUP}/url', DEFAULT_URL) or DEFAULT_URL).rstrip('/')


def token():
    return _s().value(f'{GROUP}/token', '') or ''


def last_city():
    return _s().value(f'{GROUP}/last_city', '') or ''


def save_connection(url, tok):
    s = _s()
    s.setValue(f'{GROUP}/url', (url or DEFAULT_URL).rstrip('/'))
    s.setValue(f'{GROUP}/token', tok or '')


def save_last_city(city):
    _s().setValue(f'{GROUP}/last_city', city or '')


def clear():
    s = _s()
    for k in ('url', 'token', 'last_city'):
        s.remove(f'{GROUP}/{k}')
