from __future__ import annotations

from functools import partial

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import QMainWindow, QMessageBox, QWidget

from App.auth_service import ROLE_LABEL, UserContext
from App.db import resolve_product_photo_path, session
from App.paths import ui_path
from App.product_service import delete_product, get_product, list_suppliers, products_query
from App.ui_loader import load_ui
from App.windows.product_edit_window import ProductEditWindow


class _ClickFilter(QObject):
    def __init__(self, on_click):
        super().__init__()
        self._on_click = on_click

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._on_click()
            return True
        return False


class ProductListWindow(QMainWindow):
    def __init__(self, *, user: UserContext, on_logout, on_open_orders):
        super().__init__()
        self._user = user
        self._on_logout = on_logout
        self._on_open_orders = on_open_orders
        self._edit_dialog: ProductEditWindow | None = None

        self.ui = load_ui(ui_path("main.ui"))
        self.setCentralWidget(self.ui.centralwidget)
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.minimumSize())

        self.ui.btn_logout.clicked.connect(self._logout)
        self.ui.btn_orders.clicked.connect(self._open_orders)
        self.ui.btn_add.clicked.connect(self._add_product)

        self.ui.search_edit.textChanged.connect(self._refresh_products)
        self.ui.supplier_combo.currentTextChanged.connect(self._refresh_products)
        self.ui.sort_combo.currentTextChanged.connect(self._refresh_products)

        self._apply_role_ui()
        self._fill_filter_controls()
        self._refresh_products()

    def set_app_icon(self, icon: QIcon):
        self.setWindowIcon(icon)

    def _apply_role_ui(self):
        role = (self._user.role or "guest").strip()
        self.ui.lbl_role.setText(ROLE_LABEL.get(role, role))
        self.ui.lbl_user.setText(self._user.full_name or "")

        is_guest_or_client = role in ("guest", "client")
        is_manager = role == "manager"
        is_admin = role == "administrator"

        # фильтры только менеджер/админ
        for w in [self.ui.lbl_search, self.ui.search_edit, self.ui.lbl_supplier, self.ui.supplier_combo, self.ui.lbl_sort, self.ui.sort_combo]:
            w.setVisible(not is_guest_or_client)
            w.setEnabled(not is_guest_or_client)

        # добавить/удалить/редактировать — только админ
        self.ui.btn_add.setVisible(is_admin)
        self.ui.btn_add.setEnabled(is_admin)

        # заказы — менеджер/админ
        self.ui.btn_orders.setVisible(is_manager or is_admin)
        self.ui.btn_orders.setEnabled(is_manager or is_admin)

    def _fill_filter_controls(self):
        self.ui.sort_combo.clear()
        self.ui.sort_combo.addItems(["Без сортировки", "По возрастанию", "По убыванию"])

        self.ui.supplier_combo.clear()
        self.ui.supplier_combo.addItem("Все поставщики")
        for n in list_suppliers():
            self.ui.supplier_combo.addItem(n)

    def _clear_cards(self):
        lay = self.ui.cards_layout
        # оставляем последний spacer (как в .ui)
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _discount_html(self, price: float, discount: float) -> str:
        if discount <= 0:
            return f"Цена: {price:.2f} ₽"
        new_price = price * (1.0 - discount / 100.0)
        return (
            "Цена: "
            f"<span style='color:#C00000; text-decoration: line-through;'>{price:.2f} ₽</span> "
            f"<span style='color:#000000;'>{new_price:.2f} ₽</span>"
        )

    def _make_card(self, row: dict) -> QWidget:
        card = load_ui(ui_path("product_item.ui"))
        pid = int(row["product_id"])
        art = str(row.get("product_art") or "")
        name = str(row.get("product_name") or "")
        categ = str(row.get("categ_name") or "—")
        desc = str(row.get("product_desc") or "—")
        manuf = str(row.get("product_manufac") or "—")
        supp = str(row.get("supp_name") or "—")
        unit = str(row.get("product_unit") or "—")
        stock = int(row.get("product_stock") or 0)
        discount = float(row.get("product_discount") or 0)
        price = float(row.get("product_price") or 0)

        card.lbl_header.setText(f"{categ} | {name} ({art})")
        card.lbl_description.setText(f"Описание: {desc}")
        card.lbl_manufacturer.setText(f"Производитель: {manuf}")
        card.lbl_supplier.setText(f"Поставщик: {supp}")
        card.lbl_unit.setText(f"Ед.: {unit}")
        card.lbl_stock.setText(f"Остаток: {stock}")
        card.discount_label.setText(f"Скидка: {discount:.0f}%")
        card.lbl_price.setTextFormat(Qt.RichText)
        card.lbl_price.setText(self._discount_html(price, discount))

        # фото
        pm = QPixmap(resolve_product_photo_path(row.get("product_photo")))
        if not pm.isNull():
            pm = pm.scaled(160, 107, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            card.photo_label.setPixmap(pm)

        # подсветка
        if stock <= 0:
            card.setStyleSheet("background-color: #87CEFA;")  # голубой
        elif discount > 15:
            card.setStyleSheet("background-color: #2E8B57;")  # зелёный

        # удалить
        is_admin = (self._user.role or "") == "administrator"
        card.btn_delete.setVisible(is_admin)
        card.btn_delete.setEnabled(is_admin)
        card.btn_delete.clicked.connect(partial(self._delete_product, pid))

        # клик по карточке → редактирование (только админ)
        if is_admin:
            flt = _ClickFilter(partial(self._edit_product, pid))
            card.installEventFilter(flt)
            card._flt = flt  # чтобы не удалился GC

        # чуть компактнее
        f = card.font()
        if isinstance(f, QFont):
            f.setPointSize(max(8, f.pointSize()))
            card.setFont(f)

        return card

    def _refresh_products(self):
        role = (self._user.role or "guest").strip()
        search = self.ui.search_edit.text() if role in ("manager", "administrator") else None
        supplier = self.ui.supplier_combo.currentText() if role in ("manager", "administrator") else None
        sort_txt = self.ui.sort_combo.currentText() if role in ("manager", "administrator") else "Без сортировки"
        sort_stock = None
        if sort_txt == "По возрастанию":
            sort_stock = "asc"
        elif sort_txt == "По убыванию":
            sort_stock = "desc"

        self._clear_cards()
        q = products_query(search=search, supplier_name=supplier, sort_stock=sort_stock)
        with session() as s:
            rows = [dict(r) for r in s.execute(q).mappings().all()]

        for r in rows:
            self.ui.cards_layout.insertWidget(self.ui.cards_layout.count() - 1, self._make_card(r))

    def _delete_product(self, product_id: int):
        r = QMessageBox.question(self, "Подтверждение", "Удалить товар? Это действие нельзя отменить.")
        if r != QMessageBox.Yes:
            return
        try:
            delete_product(product_id)
        except Exception as e:
            QMessageBox.warning(self, "Удаление невозможно", str(e))
            return
        self._refresh_products()

    def _edit_product(self, product_id: int):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self, "Редактирование", "Окно редактирования уже открыто.")
            return
        prod = get_product(product_id)
        self._edit_dialog = ProductEditWindow(product=prod, is_admin=True, on_saved=lambda _pid: self._refresh_products())
        self._edit_dialog.exec()

    def _add_product(self):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self, "Добавление", "Окно редактирования уже открыто.")
            return
        self._edit_dialog = ProductEditWindow(product=None, is_admin=True, on_saved=lambda _pid: self._refresh_products())
        self._edit_dialog.exec()

    def _open_orders(self):
        self._on_open_orders()

    def _logout(self):
        self._on_logout()

