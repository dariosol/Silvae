"""Voci di menu e barra strumenti del plugin Silvae Pro."""
import os

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import Qgis, QgsProject

from . import conflicts as conflicts_mod
from . import mapping as mapping_store
from . import push as push_mod
from . import settings
from .api import SilvaeClient, SilvaeError
from .pull import pull_city, pull_delivery
from .ui.deliveries_dock import DeliveriesDock
from .ui.login_dialog import LoginDialog
from .ui.pull_dialog import PullDialog
from .ui.conflicts_dialog import ConflictsDialog
from .ui.push_dialog import PushDialog

MENU = '&Silvae Pro'


class SilvaePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.dock = None

    # --- ciclo di vita -----------------------------------------------------
    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))
        self._add_action(icon, 'Collegamento a Silvae…', self.open_login, toolbar=False)
        self._add_action(icon, 'Carica da Silvae…', self.open_pull, toolbar=True)
        self._add_action(icon, 'Invia a Silvae…', self.open_push, toolbar=True)
        self._add_action(icon, 'Invii in attesa', self.toggle_deliveries, toolbar=True)

        self.dock = DeliveriesDock(self.iface.mainWindow())
        self.dock.fetch_requested.connect(self.fetch_delivery)
        self.dock.delete_requested.connect(self.delete_delivery)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()

    def unload(self):
        for a in self.actions:
            self.iface.removePluginVectorMenu(MENU, a)
            self.iface.removeToolBarIcon(a)
        self.actions = []
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def _add_action(self, icon, text, slot, toolbar):
        a = QAction(icon, text, self.iface.mainWindow())
        a.triggered.connect(slot)
        self.iface.addPluginToVectorMenu(MENU, a)
        if toolbar:
            self.iface.addToolBarIcon(a)
        self.actions.append(a)

    # --- azioni ------------------------------------------------------------
    def _client(self):
        if not settings.token():
            if not self.open_login():
                return None
        return SilvaeClient(settings.base_url(), settings.token())

    def open_login(self):
        dlg = LoginDialog(self.iface.mainWindow())
        ok = dlg.exec_()
        if ok and dlg.user:
            self.iface.messageBar().pushMessage('Silvae Pro', f"Collegato come {dlg.user.get('username')}",
                                                level=Qgis.Success, duration=4)
            if self.dock is not None:
                self.dock.set_client(SilvaeClient(settings.base_url(), settings.token()))
        return bool(ok)

    # --- invio a Silvae ----------------------------------------------------
    def open_push(self):
        client = self._client()
        if client is None:
            return
        layer = self.iface.activeLayer()
        if layer is None or not hasattr(layer, 'fields'):
            self._error('Scegli prima un layer vettoriale nel pannello dei layer.')
            return
        if layer.featureCount() == 0:
            self._error('Il layer non ha feature da inviare.')
            return
        project = QgsProject.instance()
        try:
            cities = client.cities()
            mapping, fields = mapping_store.suggest(client, layer, project)
        except SilvaeError as e:
            self._error(f'Errore da Silvae: {e}')
            return

        def preview(values):
            return push_mod.push(client, layer, values['city'], mapping=values['mapping'],
                                 only_selected=values['only_selected'],
                                 on_conflict=values['on_conflict'], dry_run=True)

        dlg = PushDialog(layer, cities, mapping, fields, preview, self.iface.mainWindow())
        if settings.last_city() in cities:
            dlg.city.setCurrentText(settings.last_city())
        if not dlg.exec_():
            return
        v = dlg.values()
        if not v['city']:
            self._error('Scegli un comune.')
            return
        mapping_store.save(project, layer, v['mapping'])
        settings.save_last_city(v['city'])
        try:
            res = push_mod.push(client, layer, v['city'], mapping=v['mapping'],
                                only_selected=v['only_selected'],
                                on_conflict=v['on_conflict'])
        except SilvaeError as e:
            self._error(f'Invio non riuscito: {e}')
            return
        self._report_push(res, layer)
        if res['counts'].get('conflicts'):
            self.resolve_conflicts(client, layer, res['conflicts'], v)

    def resolve_conflicts(self, client, layer, conflicts, values):
        """Apre la finestra di confronto e applica le scelte (fase 4)."""
        try:
            rows = conflicts_mod.describe(client, layer, conflicts, values['mapping'])
        except SilvaeError as e:
            self._error(f'Impossibile leggere la versione di Silvae: {e}')
            return
        if not rows:
            return
        dlg = ConflictsDialog(rows, self.iface.mainWindow())
        if not dlg.exec_():
            return
        try:
            out = conflicts_mod.resolve(client, layer, rows, dlg.choices(),
                                        values['city'], values['mapping'],
                                        on_conflict=values['on_conflict'])
        except SilvaeError as e:
            self._error(f'Risoluzione non riuscita: {e}')
            return
        except Exception as e:
            self._error(f'Risoluzione non riuscita: {e}')
            return
        forced = (out.get('forced') or {}).get('counts', {})
        msg = (f"Conflitti risolti: {forced.get('updated', 0) + forced.get('created', 0)} "
               f"con la versione di QGIS, {out['from_server']} con quella di Silvae")
        if out['skipped']:
            msg += f", {out['skipped']} rimandati"
        self.iface.messageBar().pushMessage('Silvae Pro', msg, level=Qgis.Success, duration=8)
        layer.triggerRepaint()

    def _report_push(self, res, layer):
        c = res.get('counts', {})
        msg = (f"{res.get('total', 0)} feature inviate: {c.get('created', 0)} nuove, "
               f"{c.get('updated', 0)} aggiornate, {c.get('unchanged', 0)} invariate")
        if c.get('skipped'):
            msg += f", {c['skipped']} saltate"
        level = Qgis.Success
        if c.get('conflicts') or c.get('errors'):
            level = Qgis.Warning
            msg += f" — {c.get('conflicts', 0)} in conflitto, {c.get('errors', 0)} con errori"
        try:
            written = push_mod.write_back_links(layer, res)
            if written:
                msg += f". Collegamento scritto in {written} feature (silvae_uuid)."
            else:
                msg += ". Il layer non è modificabile: il collegamento (silvae_uuid) non è stato scritto."
        except Exception as e:
            level = Qgis.Warning
            msg += f". Collegamento non scritto: {e}"
        self.iface.messageBar().pushMessage('Silvae Pro', msg, level=level, duration=10)

    # --- cassetta postale --------------------------------------------------
    def toggle_deliveries(self):
        if self.dock is None:
            return
        client = self._client()
        if client is None:
            return
        self.dock.set_client(client)
        self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self.dock.raise_()

    def fetch_delivery(self, delivery):
        client = self._client()
        if client is None:
            return
        project = QgsProject.instance()
        directory = os.path.dirname(project.fileName()) if project.fileName() else os.path.expanduser('~')
        try:
            res = pull_delivery(client, project, delivery, directory)
        except SilvaeError as e:
            self._error(f'Errore da Silvae: {e}')
            return
        except Exception as e:
            self._error(f'Errore nel salvataggio: {e}')
            return
        msg = (f"{delivery.get('title')}: {res['received']} alberi ritirati "
               f"({res['added']} nuovi, {res['updated']} aggiornati) in {os.path.basename(res['path'])}")
        if res.get('style_error'):
            msg += f" — stile non applicato: {res['style_error']}"
        self.iface.messageBar().pushMessage('Silvae Pro', msg, level=Qgis.Success, duration=8)
        target = res.get('polygon_layer') or res['layer']
        self.iface.mapCanvas().setExtent(target.extent())
        self.iface.mapCanvas().refresh()
        self.dock.refresh()

    def delete_delivery(self, delivery):
        client = self._client()
        if client is None:
            return
        if QMessageBox.question(self.iface.mainWindow(), 'Silvae Pro',
                                f"Eliminare l'invio «{delivery.get('title')}»?") != QMessageBox.Yes:
            return
        try:
            client.delete_delivery(delivery['id'])
        except SilvaeError as e:
            self._error(f'Eliminazione non riuscita: {e}')
            return
        self.dock.refresh()

    def open_pull(self):
        client = self._client()
        if client is None:
            return
        try:
            cities = client.cities()
        except SilvaeError as e:
            self._error(f'Impossibile leggere i comuni: {e}')
            return
        project = QgsProject.instance()
        default_dir = os.path.dirname(project.fileName()) if project.fileName() else os.path.expanduser('~')
        dlg = PullDialog(cities, default_dir, self.iface.mainWindow())
        if not dlg.exec_():
            return
        v = dlg.values()
        if not v['city']:
            self._error('Scegli un comune.')
            return
        settings.save_last_city(v['city'])
        try:
            res = pull_city(client, project, v['city'], v['directory'],
                            style_by=v['style_by'], force_full=v['force_full'])
        except SilvaeError as e:
            self._error(f'Errore da Silvae: {e}')
            return
        except Exception as e:
            self._error(f'Errore nel salvataggio: {e}')
            return
        if res['mode'] == 'created':
            msg = f"{v['city']}: {res['count']} alberi caricati in {os.path.basename(res['path'])}"
        else:
            msg = (f"{v['city']}: {res['added']} nuovi, {res['updated']} aggiornati "
                   f"({res['count']} alberi in {os.path.basename(res['path'])})")
        if res.get('style_error'):
            msg += f" — stile non applicato: {res['style_error']}"
        self.iface.messageBar().pushMessage('Silvae Pro', msg, level=Qgis.Success, duration=8)
        if res['mode'] == 'created':
            self.iface.mapCanvas().setExtent(res['layer'].extent())
            self.iface.mapCanvas().refresh()

    def _error(self, text):
        QMessageBox.warning(self.iface.mainWindow(), 'Silvae Pro', text)

    @staticmethod
    def tr(text):
        return QCoreApplication.translate('SilvaePlugin', text)
