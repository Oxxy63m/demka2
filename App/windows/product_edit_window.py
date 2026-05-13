from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QVBoxLayout

from App.db import resolve_product_photo_path
from App.paths import ui_path
from App.product_service import list_categories, list_manufacturers, next_product_id, upsert_product
from App.ui_loader import load_ui


class ProductEditWindow(QDialog):
    def __init__(self, *, product: dict | None, is_admin: bool, on_saved, parent=None):
        super().__init__(parent)
        self._product = product
        self._is_admin = is_admin
        self._on_saved = on_saved
        self._pending_photo_file: str | None = None

        self.ui = load_ui(ui_path("product_form.ui"))
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.minimumSize())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)

        self.ui.btn_cancel.clicked.connect(self.reject)
        self.ui.btn_save.clicked.connect(self._save)
        self.ui.btn_photo.clicked.connect(self._pick_photo)

        if not is_admin:
            self._set_read_only()

        self._fill_lists()
        self._load_data()

    def _set_read_only(self):
        self.ui.btn_save.setEnabled(False)
        self.ui.btn_photo.setEnabled(False)
        for w in [
            self.ui.article_edit,
            self.ui.name_edit,
            self.ui.category_combo,
            self.ui.desc_edit,
            self.ui.manuf_combo,
            self.ui.supp_edit,
            self.ui.price_spin,
            self.ui.unit_edit,
            self.ui.qty_spin,
            self.ui.discount_spin,
        ]:
            w.setEnabled(False)

    def _fill_lists(self):
        self.ui.category_combo.clear()
        self.ui.category_combo.addItems(list_categories())
        self.ui.manuf_combo.clear()
        self.ui.manuf_combo.addItems(list_manufacturers())

    def _load_data(self):
        if self._product is None:
            self.ui.id_edit.setText(str(next_product_id()))
            self._set_photo(resolve_product_photo_path("picture.png"))
            return

        self.ui.id_edit.setText(str(self._product.get("product_id", "")))
        self.ui.article_edit.setText(str(self._product.get("product_art", "") or ""))
        self.ui.name_edit.setText(str(self._product.get("product_name", "") or ""))
        self.ui.unit_edit.setText(str(self._product.get("product_unit", "") or ""))
        self.ui.supp_edit.setText(str(self._product.get("supp_name") or ""))
        self.ui.price_spin.setValue(float(self._product.get("product_price") or 0))
        self.ui.qty_spin.setValue(int(self._product.get("product_stock") or 0))
        self.ui.discount_spin.setValue(float(self._product.get("product_discount") or 0))

        desc = str(self._product.get("product_desc") or "")
        self.ui.desc_edit.setPlainText(desc)

        manuf = str(self._product.get("product_manufac") or "")
        if manuf:
            self.ui.manuf_combo.setCurrentText(manuf)

        categ = str(self._product.get("categ_name") or "")
        if categ:
            self.ui.category_combo.setCurrentText(categ)

        photo_value = self._product.get("product_photo")
        self._set_photo(resolve_product_photo_path(photo_value))

        # при редактировании ID только чтение — уже так в ui

    def _set_photo(self, abs_path: str):
        pm = QPixmap(abs_path)
        if not pm.isNull():
            pm = pm.scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.ui.photo_label.setPixmap(pm)

    def _pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение",
            "",
            "Изображения (*.png *.jpg *.jpeg *.bmp);;Все файлы (*.*)",
        )
        if not path:
            return

        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Ошибка", "Файл не является изображением.")
            return

        # Ограничение 300x200: если больше — просто уменьшаем при показе, а в папку приложения кладём как есть.
        # Для учебного задания этого достаточно и стабильно работает.
        self._pending_photo_file = path
        self._set_photo(os.path.abspath(path))

    def _save(self):
        try:
            pid = int(self.ui.id_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Некорректный ID товара.")
            return

        article = self.ui.article_edit.text().strip()
        name = self.ui.name_edit.text().strip()
        if not article or not name:
            QMessageBox.warning(self, "Ошибка", "Артикул и наименование обязательны.")
            return

        try:
            saved_id = upsert_product(
                product_id=(self._product.get("product_id") if self._product else None),
                article=article,
                name=name,
                category_name=self.ui.category_combo.currentText().strip() or None,
                description=self.ui.desc_edit.toPlainText(),
                manufacturer=self.ui.manuf_combo.currentText().strip() or None,
                supplier_name=self.ui.supp_edit.text().strip() or None,
                price=float(self.ui.price_spin.value()),
                unit=self.ui.unit_edit.text().strip() or "шт.",
                qty=int(self.ui.qty_spin.value()),
                discount=float(self.ui.discount_spin.value()),
                photo_path_to_copy=self._pending_photo_file,
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return

        self._on_saved(saved_id)
        self.accept()

