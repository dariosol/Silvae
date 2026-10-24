"""Finestra «Carica da Silvae»: comune, cartella del GPKG, stile."""
import os

from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                                 QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QVBoxLayout, QCheckBox)

from .. import settings


class PullDialog(QDialog):
    def __init__(self, cities, default_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Silvae Pro — Carica da Silvae')
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.city = QComboBox()
        self.city.setEditable(True)
        self.city.addItems(cities)
        last = settings.last_city()
        if last in cities:
            self.city.setCurrentText(last)
        form.addRow('Comune', self.city)

        row = QHBoxLayout()
        self.directory = QLineEdit(default_dir)
        btn = QPushButton('…')
        btn.setFixedWidth(32)
        btn.clicked.connect(self.choose_dir)
        row.addWidget(self.directory, 1)
        row.addWidget(btn)
        form.addRow('Cartella GPKG', row)

        self.style = QComboBox()
        self.style.addItem('Rischio ARETE / condizione VTA (barra statistiche)', 'stat')
        self.style.addItem('Solo classe di rischio ARETE', 'rischio')
        self.style.addItem('Solo condizione VTA / CPC', 'condizione')
        form.addRow('Stile', self.style)

        self.force_full = QCheckBox('Riscarica tutto (ignora l\'aggiornamento incrementale)')
        form.addRow('', self.force_full)
        lay.addLayout(form)

        note = QLabel('Gli alberi vengono salvati in <code>silvae_&lt;comune&gt;.gpkg</code> nella cartella '
                      'scelta e aggiunti al progetto. Se il layer è già nel progetto vengono scaricate '
                      'solo le modifiche dall\'ultimo caricamento.')
        note.setWordWrap(True)
        lay.addWidget(note)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText('Carica')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

    def choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, 'Cartella per il GeoPackage', self.directory.text())
        if d:
            self.directory.setText(d)

    def values(self):
        return {'city': self.city.currentText().strip(),
                'directory': self.directory.text().strip() or os.getcwd(),
                'style_by': self.style.currentData(),
                'force_full': self.force_full.isChecked()}
