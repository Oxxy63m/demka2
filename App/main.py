from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from App.auth_service import UserContext, guest_context
from App.paths import icon_path
from App.db import tables
from App.windows.login_window import LoginWindow
from App.windows.main_shell import MainShell


class AppController:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._icon = QIcon(icon_path())
        self._app.setWindowIcon(self._icon)

        self._user: UserContext = guest_context()
        self._login: LoginWindow | None = None
        self._shell: MainShell | None = None

    def run(self) -> int:
        try:
            tables()  # проверка соединения и наличия таблиц
        except Exception as e:
            QMessageBox.critical(None, "Ошибка подключения к БД", str(e))
            return 1
        self._show_login()
        return self._app.exec()

    def _show_login(self):
        if self._shell:
            self._shell.close()
            self._shell = None

        def on_login(user: UserContext):
            self._user = user

        self._login = LoginWindow(on_login=on_login)
        self._login.set_app_icon(self._icon)
        if self._login.exec() == LoginWindow.Accepted:
            self._show_products()
        else:
            self._app.quit()

    def _ensure_shell(self) -> MainShell:
        if self._shell is None:
            self._shell = MainShell()
            self._shell.set_app_icon(self._icon)
        return self._shell

    def _show_products(self):
        shell = self._ensure_shell()
        shell.show_products(
            user=self._user,
            on_logout=self._show_login,
            on_open_orders=self._show_orders,
        )
        shell.show()

    def _show_orders(self):
        shell = self._ensure_shell()

        def back():
            shell.back_to_products()

        shell.show_orders(user=self._user, on_back=back)


def main():
    return AppController().run()


if __name__ == "__main__":
    raise SystemExit(main())
