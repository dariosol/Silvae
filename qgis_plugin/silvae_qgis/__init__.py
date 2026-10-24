"""Plugin QGIS per Silvae Pro (vedi docs/qgis.md nel repository dell'app)."""


def classFactory(iface):
    from .plugin import SilvaePlugin
    return SilvaePlugin(iface)
