from __future__ import annotations

from functools import partial

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMessageBox, QSizePolicy, QVBoxLayout, QWidget

from App.auth_service import ROLE_LABEL, UserContext
from App.order_service import delete_order, get_order, list_orders
from App.paths import ui_path
from App.ui_click import install_card_click
from App.ui_loader import load_ui
from App.windows.order_edit_window import OrderEditWindow


class OrderListWindow(QWidget):
    def __init__(self, *, user: UserContext, on_back):
        super().__init__()
        self._user = user
        self._on_back = on_back
        self._edit_dialog: OrderEditWindow | None = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        shell = load_ui(ui_path("orders_list.ui"))
        self.ui = shell
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(shell.centralwidget, 1)

        self._setup_scroll_area()

        self.ui.btn_back.clicked.connect(self._back)
        self.ui.btn_add.clicked.connect(self._add_order)

        self._apply_role_ui()
        self._refresh()

    def _window(self):
        return self.window()

    def _setup_scroll_area(self):
        self.ui.orders_scroll.setWidgetResizable(True)
        expand = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.ui.orders_scroll.setSizePolicy(expand)
        lay = self.ui.centralwidget.layout()
        if lay is not None:
            idx = lay.indexOf(self.ui.orders_scroll)
            if idx >= 0:
                lay.setStretch(idx, 1)

    def _apply_role_ui(self):
        role = (self._user.role or "guest").strip()
        self.ui.lbl_role.setText(ROLE_LABEL.get(role, role))
        self.ui.lbl_user.setText(self._user.full_name or "")

        is_admin = role == "administrator"
        self.ui.btn_add.setVisible(is_admin)
        self.ui.btn_add.setEnabled(is_admin)

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
        articles = str(order.get("article_summary") or "—")
        status = str(order.get("status_name") or "—")
        address = str(order.get("pp_name") or "—")
        order_date = str(order.get("order_date") or "—")
        delivery = str(order.get("order_pup_date") or "—")

        f = card.lbl_order_article.font()
        f.setBold(True)
        card.lbl_order_article.setFont(f)
        card.lbl_order_article.setText(f"Заказ #{oid}: {articles}")
        card.lbl_status.setText(f"Статус: {status}")
        card.lbl_pickup_address.setText(f"Пункт выдачи: {address}")
        card.lbl_order_date.setText(f"Дата заказа: {order_date}")
        card.lbl_delivery_date.setText(f"Дата выдачи:\n{delivery}")

        role = (self._user.role or "").strip()
        is_admin = role == "administrator"

        card.btn_delete.setVisible(is_admin)
        card.btn_delete.setEnabled(is_admin)
        card.btn_delete.clicked.connect(partial(self._delete_order, oid))

        if is_admin:
            install_card_click(card, partial(self._edit_order, oid))

        f_card = card.font()
        if isinstance(f_card, QFont):
            f_card.setPointSize(max(8, f_card.pointSize()))
            card.setFont(f_card)

        return card

    def _refresh(self):
        self._clear_cards()
        for o in list_orders():
            self.ui.orders_cards_layout.insertWidget(self.ui.orders_cards_layout.count() - 1, self._make_card(o))

    def _edit_order(self, order_id: int):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self._window(), "Редактирование", "Окно редактирования уже открыто.")
            return
        try:
            order = get_order(order_id)
            if not order:
                QMessageBox.warning(self._window(), "Ошибка", "Заказ не найден.")
                self._refresh()
                return
            self._edit_dialog = OrderEditWindow(
                order=order,
                is_admin=True,
                on_saved=lambda _id: self._refresh(),
                parent=self._window(),
            )
            self._edit_dialog.exec()
        except Exception as e:
            QMessageBox.critical(self._window(), "Ошибка", str(e))
        finally:
            self._edit_dialog = None

    def _add_order(self):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self._window(), "Добавление", "Окно редактирования уже открыто.")
            return
        try:
            self._edit_dialog = OrderEditWindow(
                order=None,
                is_admin=True,
                on_saved=lambda _id: self._refresh(),
                default_client_name=self._user.full_name or "",
                parent=self._window(),
            )
            self._edit_dialog.exec()
        except Exception as e:
            QMessageBox.critical(self._window(), "Ошибка", str(e))
        finally:
            self._edit_dialog = None

    def _delete_order(self, order_id: int):
        r = QMessageBox.question(self._window(), "Подтверждение", "Удалить заказ? Это действие нельзя отменить.")
        if r != QMessageBox.Yes:
            return
        try:
            delete_order(int(order_id))
        except Exception as e:
            QMessageBox.warning(self._window(), "Удаление невозможно", str(e))
            return
        self._refresh()

    def _back(self):
        self._on_back()
