"""Finestra «Collegamento a Silvae»: URL del server e token API."""
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout)

from .. import settings
from ..api import SilvaeClient, SilvaeError


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Silvae Pro — Collegamento')
        self.setMinimumWidth(460)
        self.user = None

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.url = QLineEdit(settings.base_url())
        self.token = QLineEdit(settings.token())
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText('slv_… (da «Il mio account» nella webapp)')
        form.addRow('Server', self.url)
        form.addRow('Token API', self.token)
        lay.addLayout(form)

        row = QHBoxLayout()
        self.check_btn = QPushButton('Verifica')
        self.check_btn.clicked.connect(self.check)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        row.addWidget(self.check_btn)
        row.addWidget(self.status, 1)
        lay.addLayout(row)

        hint = QLabel('Il token si crea nella webapp: nome utente in alto → '
                      '<b>Il mio account</b> → <b>Token API per QGIS</b>.')
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

    def client(self):
        return SilvaeClient(self.url.text().strip(), self.token.text().strip())

    def check(self):
        try:
            me = self.client().me()
        except SilvaeError as e:
            self.user = None
            self.status.setText(f'<span style="color:#c0392b">{e}</span>')
            return False
        self.user = me
        role = {'user': 'agronomo', 'city': 'comune', 'superuser': 'superutente'}.get(me.get('role'), me.get('role'))
        city = f" · {me['city']}" if me.get('city') else ''
        self.status.setText(f'<span style="color:#2d6a4f">Collegato come <b>{me.get("username")}</b> ({role}{city})</span>')
        return True

    def save(self):
        if self.user is None and not self.check():
            return
        settings.save_connection(self.url.text().strip(), self.token.text().strip())
        self.accept()
