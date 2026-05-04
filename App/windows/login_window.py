from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from App.auth_service import authenticate, guest_context
from App.paths import logo_path_fallback, ui_path
from App.ui_loader import load_ui


class LoginWindow(QDialog):
    def __init__(self, on_login):
        super().__init__()
        self._on_login = on_login
        self.ui = load_ui(ui_path("login.ui"))
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.minimumSize())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)

        self.ui.btn_login.clicked.connect(self._handle_login)
        self.ui.btn_guest.clicked.connect(self._handle_guest)

        # логотип
        try:
            pm = QPixmap(logo_path_fallback())
            self.ui.lbl_logo.setPixmap(pm)
        except Exception:
            pass

    def set_app_icon(self, icon: QIcon):
        self.setWindowIcon(icon)

    def _handle_guest(self):
        self._on_login(guest_context())
        self.accept()

    def _handle_login(self):
        login = self.ui.login_edit.text()
        pwd = self.ui.password_edit.text()
        user = authenticate(login, pwd)
        if not user:
            QMessageBox.warning(self, "Ошибка авторизации", "Неверный логин или пароль.")
            return
        self._on_login(user)
        self.accept()

