"""Finestra «Invia a Silvae»: cosa inviare, mappatura colonne, anteprima."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                                 QPushButton, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout)

NO_IMPORT = '— non inviare —'


class PushDialog(QDialog):
    """Emette nulla: il chiamante legge `values()` dopo exec_().
    L'anteprima (dry run) la esegue il plugin tramite `preview_callback`."""

    def __init__(self, layer, cities, mapping, fields, preview_callback, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Silvae Pro — Invia a Silvae: {layer.name()}')
        self.setMinimumWidth(620)
        self.layer = layer
        self.fields = fields
        self.preview_callback = preview_callback
        self._previewed = False

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.city = QComboBox()
        self.city.setEditable(True)
        self.city.addItems(cities)
        form.addRow('Comune', self.city)

        n_sel = layer.selectedFeatureCount()
        self.only_selected = QCheckBox(f'Solo le feature selezionate ({n_sel})')
        self.only_selected.setEnabled(n_sel > 0)
        self.only_selected.setChecked(n_sel > 0)
        form.addRow('', self.only_selected)

        self.on_conflict = QComboBox()
        self.on_conflict.addItem('Aggiorna gli alberi già presenti', 'update')
        self.on_conflict.addItem('Salta gli alberi già presenti (solo nuovi)', 'skip')
        form.addRow('Se esiste già', self.on_conflict)
        lay.addLayout(form)

        lay.addWidget(QLabel('<b>Colonne</b> — a quale campo di Silvae corrisponde ciascuna colonna. '
                             'La scelta viene ricordata nel progetto.'))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Colonna del layer', 'Campo Silvae'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        self._fill_table(mapping)

        self.summary = QLabel('Nessuna anteprima: premi «Anteprima» per sapere cosa cambierà.')
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        row = QHBoxLayout()
        self.preview_btn = QPushButton('Anteprima')
        self.preview_btn.clicked.connect(self.run_preview)
        row.addWidget(self.preview_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_btn = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_btn.setText('Invia')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

    # --- mappatura ---------------------------------------------------------
    def _fill_table(self, mapping):
        cols = [f.name() for f in self.layer.fields()]
        self.table.setRowCount(len(cols))
        for r, col in enumerate(cols):
            item = QTableWidgetItem(col)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, item)
            combo = QComboBox()
            combo.addItem(NO_IMPORT, '')
            for f in self.fields:
                combo.addItem(f, f)
            target = mapping.get(col, '')
            combo.setCurrentIndex(max(0, combo.findData(target)) if target else 0)
            combo.currentIndexChanged.connect(self._invalidate_preview)
            self.table.setCellWidget(r, 1, combo)

    def mapping(self):
        out = {}
        for r in range(self.table.rowCount()):
            col = self.table.item(r, 0).text()
            out[col] = self.table.cellWidget(r, 1).currentData() or ''
        return out

    def _invalidate_preview(self, *_):
        if self._previewed:
            self._previewed = False
            self.summary.setText('Mappatura cambiata: rifai l\'anteprima.')

    # --- anteprima ---------------------------------------------------------
    def run_preview(self):
        v = self.values()
        if not v['city']:
            self.summary.setText('<span style="color:#c0392b">Scegli prima il comune.</span>')
            return None
        self.preview_btn.setEnabled(False)
        try:
            res = self.preview_callback(v)
        except Exception as e:
            self.summary.setText(f'<span style="color:#c0392b">Anteprima non riuscita: {e}</span>')
            return None
        finally:
            self.preview_btn.setEnabled(True)
        self._previewed = True
        self.show_preview(res)
        return res

    def show_preview(self, res):
        c = res.get('counts', {})
        parts = [f"<b>{c.get('created', 0)}</b> nuovi", f"<b>{c.get('updated', 0)}</b> aggiornati",
                 f"{c.get('unchanged', 0)} invariati", f"{c.get('skipped', 0)} saltati",
                 f"<b>{c.get('conflicts', 0)}</b> in conflitto", f"<b>{c.get('errors', 0)}</b> errori"]
        text = f"Su {res.get('total', 0)} feature: " + ' · '.join(parts)
        if res.get('ignored_fields'):
            text += ('<br><i>Campi calcolati da Silvae, ignorati: '
                     + ', '.join(res['ignored_fields']) + '</i>')
        if c.get('conflicts'):
            text += '<br><span style="color:#856404">I conflitti non vengono scritti: ' \
                    'qualcuno ha modificato quegli alberi dopo il tuo ultimo caricamento.</span>'
        for e in (res.get('errors') or [])[:3]:
            text += f"<br><span style=\"color:#c0392b\">riga {e.get('src')}: {e.get('message')}</span>"
        self.summary.setText(text)

    # --- risultato ---------------------------------------------------------
    def values(self):
        return {'city': self.city.currentText().strip(),
                'mapping': self.mapping(),
                'only_selected': self.only_selected.isChecked(),
                'on_conflict': self.on_conflict.currentData()}
