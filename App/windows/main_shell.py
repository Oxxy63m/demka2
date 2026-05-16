from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from App.auth_service import UserContext
from App.windows.order_list_window import OrderListWindow
from App.windows.product_list_window import ProductListWindow


class MainShell(QMainWindow):
    """Одно главное окно: каталог и заказы переключаются без hide/show."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 560)
        self.resize(900, 700)

        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._products_page: ProductListWindow | None = None
        self._orders_page: OrderListWindow | None = None

    def set_app_icon(self, icon: QIcon):
        self.setWindowIcon(icon)

    def show_products(self, *, user: UserContext, on_logout, on_open_orders):
        if self._orders_page is not None:
            self._stack.removeWidget(self._orders_page)
            self._orders_page.deleteLater()
            self._orders_page = None

        if self._products_page is None:
            self._products_page = ProductListWindow(
                user=user,
                on_logout=on_logout,
                on_open_orders=on_open_orders,
            )
            self._stack.addWidget(self._products_page)
        else:
            self._products_page.set_user(user)

        self._stack.setCurrentWidget(self._products_page)
        self.setWindowTitle("Список товаров")

    def show_orders(self, *, user: UserContext, on_back):
        if self._orders_page is not None:
            self._stack.removeWidget(self._orders_page)
            self._orders_page.deleteLater()

        self._orders_page = OrderListWindow(user=user, on_back=on_back)
        self._stack.addWidget(self._orders_page)
        self._stack.setCurrentWidget(self._orders_page)
        self.setWindowTitle("Заказы")

    def back_to_products(self):
        if self._orders_page is not None:
            self._stack.removeWidget(self._orders_page)
            self._orders_page.deleteLater()
            self._orders_page = None
        if self._products_page is not None:
            self._stack.setCurrentWidget(self._products_page)
            self.setWindowTitle("Список товаров")
