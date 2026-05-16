from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QMessageBox, QSizePolicy, QVBoxLayout, QWidget

from App.auth_service import ROLE_LABEL, UserContext
from App.ui_click import install_card_click
from App.db import resolve_product_photo_path, session
from App.paths import ui_path
from App.product_service import delete_product, get_product, list_suppliers, products_query
from App.ui_loader import load_ui
from App.windows.product_edit_window import ProductEditWindow


class ProductListWindow(QWidget):
    def __init__(self, *, user: UserContext, on_logout, on_open_orders):
        super().__init__()
        self._user = user
        self._on_logout = on_logout
        self._on_open_orders = on_open_orders
        self._edit_dialog: ProductEditWindow | None = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        shell = load_ui(ui_path("main.ui"))
        self.ui = shell
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(shell.centralwidget, 1)

        self._setup_scroll_area()

        self.ui.btn_logout.clicked.connect(self._logout)
        self.ui.btn_orders.clicked.connect(self._open_orders)
        self.ui.btn_add.clicked.connect(self._add_product)

        self.ui.search_edit.textChanged.connect(self._refresh_products)
        self.ui.supplier_combo.currentTextChanged.connect(self._refresh_products)
        self.ui.sort_combo.currentTextChanged.connect(self._refresh_products)

        self._apply_role_ui()
        self._fill_filter_controls()
        self._refresh_products()

    def set_user(self, user: UserContext):
        self._user = user
        self._apply_role_ui()

    def _setup_scroll_area(self):
        self.ui.cards_scroll.setWidgetResizable(True)
        expand = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.ui.cards_container.setSizePolicy(expand)
        self.ui.cards_scroll.setSizePolicy(expand)
        lay = self.ui.centralwidget.layout()
        if lay is not None:
            idx = lay.indexOf(self.ui.cards_scroll)
            if idx >= 0:
                lay.setStretch(idx, 1)

    def _apply_role_ui(self):
        role = (self._user.role or "guest").strip()
        self.ui.lbl_role.setText(ROLE_LABEL.get(role, role))
        self.ui.lbl_user.setText(self._user.full_name or "")

        is_guest_or_client = role in ("guest", "client")
        is_manager = role == "manager"
        is_admin = role == "administrator"
        can_edit_products = is_admin

        # фильтры только менеджер/админ
        for w in [self.ui.lbl_search, self.ui.search_edit, self.ui.lbl_supplier, self.ui.supplier_combo, self.ui.lbl_sort, self.ui.sort_combo]:
            w.setVisible(not is_guest_or_client)
            w.setEnabled(not is_guest_or_client)

        # каталог: добавить / карточки — менеджер и администратор
        self.ui.btn_add.setVisible(can_edit_products)
        self.ui.btn_add.setEnabled(can_edit_products)

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
        role = (self._user.role or "").strip()
        can_edit_products = role == "administrator"
        card.btn_delete.setVisible(can_edit_products)
        card.btn_delete.setEnabled(can_edit_products)
        card.btn_delete.clicked.connect(partial(self._delete_product, pid))

        # клик по карточке → редактирование (только администратор)
        if can_edit_products:
            install_card_click(card, partial(self._edit_product, pid))

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

    def _window(self):
        return self.window()

    def _delete_product(self, product_id: int):
        r = QMessageBox.question(self._window(), "Подтверждение", "Удалить товар? Это действие нельзя отменить.")
        if r != QMessageBox.Yes:
            return
        try:
            delete_product(product_id)
        except Exception as e:
            QMessageBox.warning(self._window(), "Удаление невозможно", str(e))
            return
        self._refresh_products()

    def _edit_product(self, product_id: int):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self._window(), "Редактирование", "Окно редактирования уже открыто.")
            return
        try:
            prod = get_product(product_id)
            self._edit_dialog = ProductEditWindow(
                product=prod,
                is_admin=(self._user.role or "").strip() == "administrator",
                on_saved=lambda _pid: self._refresh_products(),
                parent=self._window(),
            )
            self._edit_dialog.exec()
        except Exception as e:
            QMessageBox.critical(self._window(), "Ошибка", str(e))
        finally:
            self._edit_dialog = None

    def _add_product(self):
        if self._edit_dialog is not None and self._edit_dialog.isVisible():
            QMessageBox.information(self._window(), "Добавление", "Окно редактирования уже открыто.")
            return
        try:
            self._edit_dialog = ProductEditWindow(
                product=None,
                is_admin=True,
                on_saved=lambda _pid: self._refresh_products(),
                parent=self._window(),
            )
            self._edit_dialog.exec()
        except Exception as e:
            QMessageBox.critical(self._window(), "Ошибка", str(e))
        finally:
            self._edit_dialog = None

    def _open_orders(self):
        self._on_open_orders()

    def _logout(self):
        self._on_logout()

