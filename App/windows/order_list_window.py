from __future__ import annotations

from functools import partial

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QMessageBox, QWidget

from App.auth_service import ROLE_LABEL, UserContext
from App.order_service import delete_order, get_order, list_orders
from App.paths import ui_path
from App.ui_loader import load_ui
from App.windows.order_edit_window import OrderEditWindow


class _ClickFilter(QObject):
    def __init__(self, on_click):
        super().__init__()
        self._on_click = on_click

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._on_click()
            return True
        return False


class OrderListWindow(QMainWindow):
    def __init__(self, *, user: UserContext, on_back):
        super().__init__()
        self._user = user
        self._on_back = on_back
        self._edit_dialog: OrderEditWindow | None = None

        self.ui = load_ui(ui_path("orders_list.ui"))
        self.setCentralWidget(self.ui.centralwidget)
        self.setWindowTitle(self.ui.windowTitle())

        self.ui.btn_back.clicked.connect(self._back)
        self.ui.btn_add.clicked.connect(self._add)
        self.ui.btn_del.clicked.connect(self._delete_selected)

        self._apply_role_ui()
        self._refresh()

        self._selected_order_id: int | None = None

    def set_app_icon(self, icon: QIcon):
        self.setWindowIcon(icon)

    def _apply_role_ui(self):
        role = (self._user.role or "guest").strip()
        self.ui.lbl_role.setText(ROLE_LABEL.get(role, role))
        self.ui.lbl_user.setText(self._user.full_name or "")

        is_admin = role == "administrator"
        self.ui.btn_add.setVisible(is_admin)
        self.ui.btn_del.setVisible(is_admin)
        self.ui.btn_add.setEnabled(is_admin)
        self.ui.btn_del.setEnabled(is_admin)

    def _clear_cards(self):
        lay = self.ui.orders_cards_layout
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _make_card(self, order: dict) -> QWidget:
        card = load_ui(ui_path("order_item.ui"))
        oid = int(order["order_id"])
        card.lbl_order_article.setText(f"Заказ #{oid}: {order.get('article_summary')}")
        card.lbl_status.setText(f"Статус: {order.get('status_name') or '—'}")
        card.lbl_pickup_address.setText(f"Пункт выдачи: {order.get('pp_name') or '—'}")
        card.lbl_order_date.setText(f"Дата заказа: {order.get('order_date') or '—'}")
        card.lbl_delivery_date.setText(f"Дата выдачи: {order.get('order_pup_date') or '—'}")

        def select_this():
            self._selected_order_id = oid
            # простая подсветка "выбранного" (чтобы Delete работал предсказуемо)
            for i in range(self.ui.orders_cards_layout.count() - 1):
                w = self.ui.orders_cards_layout.itemAt(i).widget()
                if w:
                    w.setStyleSheet("")
            card.setStyleSheet("background-color: #F0F0F0;")

        flt = _ClickFilter(select_this)
        card.installEventFilter(flt)
        card._flt = flt

        # для админа: двойной клик/клик → редактирование (не усложняем: кнопки нет, просто открываем при повторном клике)
        if (self._user.role or "") == "administrator":
            def open_edit():
                self._open_edit(oid)
            # второй фильтр: по двойному клику
            card.mouseDoubleClickEvent = lambda _e: open_edit()

        return card

    def _refresh(self):
        self._clear_cards()
        self._selected_order_id = None
        for o in list_orders():
            self.ui.orders_cards_layout.insertWidget(self.ui.orders_cards_layout.count() - 1, self._make_card(o))

    def _open_edit(self, order_id: int):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self, "Редактирование", "Окно редактирования уже открыто.")
            return
        order = get_order(order_id)
        if not order:
            QMessageBox.warning(self, "Ошибка", "Заказ не найден.")
            self._refresh()
            return
        self._edit_dialog = OrderEditWindow(order=order, is_admin=True, on_saved=lambda _id: self._refresh())
        self._edit_dialog.exec()

    def _add(self):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self, "Добавление", "Окно редактирования уже открыто.")
            return
        self._edit_dialog = OrderEditWindow(order=None, is_admin=True, on_saved=lambda _id: self._refresh())
        self._edit_dialog.exec()

    def _delete_selected(self):
        if self._selected_order_id is None:
            QMessageBox.information(self, "Удаление", "Сначала выберите заказ.")
            return
        r = QMessageBox.question(self, "Подтверждение", f"Удалить заказ #{self._selected_order_id}?")
        if r != QMessageBox.Yes:
            return
        try:
            delete_order(int(self._selected_order_id))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self._refresh()

    def _back(self):
        self._on_back()

