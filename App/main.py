from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from App.auth_service import UserContext, guest_context
from App.paths import icon_path
from App.db import tables
from App.windows.login_window import LoginWindow
from App.windows.order_list_window import OrderListWindow
from App.windows.product_list_window import ProductListWindow


class AppController:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._icon = QIcon(icon_path())
        self._app.setWindowIcon(self._icon)

        self._user: UserContext = guest_context()
        self._login: LoginWindow | None = None
        self._products: ProductListWindow | None = None
        self._orders: OrderListWindow | None = None

    def run(self) -> int:
        try:
            tables()  # проверка соединения и наличия таблиц
        except Exception as e:
            QMessageBox.critical(None, "Ошибка подключения к БД", str(e))
            return 1
        self._show_login()
        return self._app.exec()

    def _show_login(self):
        if self._products:
            self._products.close()
            self._products = None
        if self._orders:
            self._orders.close()
            self._orders = None

        def on_login(user: UserContext):
            self._user = user

        self._login = LoginWindow(on_login=on_login)
        self._login.set_app_icon(self._icon)
        if self._login.exec() == LoginWindow.Accepted:
            self._show_products()
        else:
            self._app.quit()

    def _show_products(self):
        if self._orders:
            self._orders.close()
            self._orders = None

        self._products = ProductListWindow(
            user=self._user,
            on_logout=self._show_login,
            on_open_orders=self._show_orders,
        )
        self._products.set_app_icon(self._icon)
        self._products.show()

    def _show_orders(self):
        if self._products:
            self._products.hide()

        def back():
            if self._orders:
                self._orders.close()
                self._orders = None
            if self._products:
                self._products.show()

        self._orders = OrderListWindow(user=self._user, on_back=back)
        self._orders.set_app_icon(self._icon)
        self._orders.show()


def main():
    return AppController().run()


if __name__ == "__main__":
    raise SystemExit(main())

