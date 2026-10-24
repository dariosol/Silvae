"""Dock «Invii in attesa»: gli invii depositati dalla webapp con «Invia a
QGIS». Si aggiorna da solo ogni 30 secondi mentre è aperto; doppio clic su
un invio lo ritira (GPKG del comune + perimetro dell'area, se c'è).
"""
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

REFRESH_MS = 30_000


class DeliveriesDock(QDockWidget):
    """Emette `fetch_requested(delivery)` quando l'utente ritira un invio."""

    fetch_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__('Silvae — Invii in attesa', parent)
        self.setObjectName('SilvaeDeliveriesDock')
        self._client = None

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 6)

        self.info = QLabel('Non collegato.')
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.currentItemChanged.connect(self._sync_buttons)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.fetch_btn = QPushButton('Ritira')
        self.fetch_btn.clicked.connect(self._on_fetch)
        self.del_btn = QPushButton('Elimina')
        self.del_btn.clicked.connect(self._on_delete)
        self.refresh_btn = QPushButton('Aggiorna')
        self.refresh_btn.clicked.connect(self.refresh)
        for b in (self.fetch_btn, self.del_btn, self.refresh_btn):
            row.addWidget(b)
        lay.addLayout(row)
        self.setWidget(box)

        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self.visibilityChanged.connect(self._on_visibility)
        self._sync_buttons()

    # --- stato -------------------------------------------------------------
    def set_client(self, client):
        self._client = client
        self.refresh()

    def _on_visibility(self, visible):
        if visible and self._client:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()

    def _sync_buttons(self, *_):
        has = self.current_delivery() is not None
        self.fetch_btn.setEnabled(has)
        self.del_btn.setEnabled(has)

    def current_delivery(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    # --- contenuto ---------------------------------------------------------
    def refresh(self):
        if not self._client:
            self.info.setText('Non collegato: Silvae Pro → Collegamento a Silvae…')
            self.list.clear()
            self._sync_buttons()
            return
        try:
            rows = self._client.deliveries()
        except Exception as e:
            self.info.setText(f'Aggiornamento non riuscito: {e}')
            return
        self.set_deliveries(rows)

    def set_deliveries(self, rows):
        previous = self.current_delivery()
        self.list.clear()
        for d in rows:
            item = QListWidgetItem(self._label(d))
            item.setData(Qt.UserRole, d)
            self.list.addItem(item)
            if previous and previous.get('id') == d.get('id'):
                self.list.setCurrentItem(item)
        if rows:
            self.info.setText(f'{len(rows)} invi{"o" if len(rows) == 1 else "i"} in attesa. '
                              'Doppio clic per ritirare.')
        else:
            self.info.setText('Nessun invio in attesa. Dalla webapp: «Invia a QGIS».')
        self._sync_buttons()

    @staticmethod
    def _label(d):
        """Il titolo generato dal server contiene già il conteggio: non si
        ripete (un titolo scelto a mano invece può non averlo)."""
        when = (d.get('created_at') or '')[:16].replace('T', ' ')
        title = d.get('title') or 'Invio'
        parts = [title]
        count = d.get('count', 0)
        if f'{count} alber' not in title:
            parts.append(f"{count} alber{'o' if count == 1 else 'i'}")
        if d.get('polygon'):
            parts.append('area')
        parts.append(when)
        return ' · '.join(parts)

    # --- azioni ------------------------------------------------------------
    def _on_double_click(self, item):
        d = item.data(Qt.UserRole)
        if d:
            self.fetch_requested.emit(d)

    def _on_fetch(self):
        d = self.current_delivery()
        if d:
            self.fetch_requested.emit(d)

    def _on_delete(self):
        d = self.current_delivery()
        if d:
            self.delete_requested.emit(d)
