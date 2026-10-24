"""Finestra di risoluzione dei conflitti dopo un invio a Silvae.

Sopra l'elenco degli alberi in conflitto con la scelta per ciascuno; sotto il
confronto campo per campo fra ciò che ha QGIS e ciò che ha Silvae.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                                 QHeaderView, QLabel, QPushButton, QSplitter,
                                 QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..conflicts import MINE, SERVER, SKIP

CHOICES = [('Tieni la versione di QGIS', MINE),
           ('Prendi la versione di Silvae', SERVER),
           ('Decidi più tardi', SKIP)]


class ConflictsDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Silvae Pro — Conflitti')
        self.setMinimumSize(760, 480)
        self.rows = rows

        lay = QVBoxLayout(self)
        head = QLabel(
            f'<b>{len(rows)} alber{"o" if len(rows) == 1 else "i"} modificat'
            f'{"o" if len(rows) == 1 else "i"} anche in Silvae</b> dopo il tuo ultimo '
            'caricamento. Per ciascuno scegli quale versione tenere: quella di QGIS '
            'sovrascrive Silvae, quella di Silvae sovrascrive il layer locale.')
        head.setWordWrap(True)
        lay.addWidget(head)

        split = QSplitter(Qt.Vertical)

        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(['Albero', 'Campi in conflitto',
                                              'Modificato in Silvae da', 'Scelta'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.currentCellChanged.connect(lambda *_: self._show_detail())
        for r, row in enumerate(rows):
            self._set(r, 0, row['custom_id'] or f"id {row['id']}")
            self._set(r, 1, ', '.join(f for f, _l, _s in row['diffs']) or '—')
            when = (row.get('server_updated_at') or '')[:16].replace('T', ' ')
            self._set(r, 2, f"{row.get('server_updated_by') or '—'} · {when}")
            combo = QComboBox()
            for label, value in CHOICES:
                combo.addItem(label, value)
            # Scelta iniziale prudente: applicare senza guardare non sovrascrive
            # né Silvae né il layer.
            combo.setCurrentIndex(combo.findData(SKIP))
            self.table.setCellWidget(r, 3, combo)
        self.table.resizeColumnsToContents()
        split.addWidget(self.table)

        detail = QWidget()
        dlay = QVBoxLayout(detail)
        dlay.setContentsMargins(0, 6, 0, 0)
        dlay.addWidget(QLabel('<b>Confronto</b>'))
        self.detail = QTableWidget(0, 3)
        self.detail.setHorizontalHeaderLabels(['Campo', 'QGIS', 'Silvae'])
        self.detail.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.detail.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        dlay.addWidget(self.detail)
        split.addWidget(detail)
        split.setSizes([260, 200])
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        for label, value in CHOICES:
            b = QPushButton(f'{label} (tutti)')
            b.clicked.connect(lambda _c=False, v=value: self.set_all(v))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText('Applica')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        if rows:
            self.table.setCurrentCell(0, 0)

    # --- helper ------------------------------------------------------------
    def _set(self, r, c, text):
        item = QTableWidgetItem(str(text))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(r, c, item)

    def _show_detail(self):
        r = self.table.currentRow()
        diffs = self.rows[r]['diffs'] if 0 <= r < len(self.rows) else []
        self.detail.setRowCount(len(diffs))
        for i, (field, local, server) in enumerate(diffs):
            for c, v in enumerate((field, local, server)):
                item = QTableWidgetItem('' if v is None else str(v))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.detail.setItem(i, c, item)
        self.detail.resizeColumnsToContents()

    def set_all(self, value):
        for r in range(self.table.rowCount()):
            combo = self.table.cellWidget(r, 3)
            combo.setCurrentIndex(combo.findData(value))

    def choices(self):
        """{fid: MINE|SERVER|SKIP}"""
        return {self.rows[r]['fid']: self.table.cellWidget(r, 3).currentData()
                for r in range(self.table.rowCount())}
