from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from App.order_service import list_pickup_points, list_statuses, upsert_order
from App.paths import ui_path
from App.ui_loader import load_ui


class OrderEditWindow(QDialog):
    def __init__(self, *, order: dict | None, is_admin: bool, on_saved):
        super().__init__()
        self._order = order
        self._is_admin = is_admin
        self._on_saved = on_saved

        self.ui = load_ui(ui_path("order_form.ui"))
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.minimumSize())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)

        self.ui.btn_cancel.clicked.connect(self.reject)
        self.ui.btn_save.clicked.connect(self._save)

        self._fill_lists()
        self._load_data()

        if not is_admin:
            self._set_read_only()

    def _set_read_only(self):
        self.ui.btn_save.setEnabled(False)
        for w in [
            self.ui.article_edit,
            self.ui.status_combo,
            self.ui.pickup_combo,
            self.ui.order_date_edit,
            self.ui.delivery_date_edit,
            self.ui.receiver_edit,
        ]:
            w.setEnabled(False)

    def _fill_lists(self):
        self.ui.status_combo.clear()
        for s in list_statuses():
            self.ui.status_combo.addItem(s)

        self.ui.pickup_combo.clear()
        for p in list_pickup_points():
            self.ui.pickup_combo.addItem(p)

    def _load_data(self):
        if self._order is None:
            self.ui.id_edit.setText("")
            self.ui.client_edit.setText("—")
            self.ui.order_date_edit.setDate(QDate.currentDate())
            self.ui.delivery_date_edit.setDate(QDate.currentDate())
            return

        self.ui.id_edit.setText(str(self._order.get("order_id", "")))
        self.ui.client_edit.setText(str(self._order.get("user_name") or "—"))
        self.ui.receiver_edit.setText(str(self._order.get("order_pp_code") or ""))

        status = str(self._order.get("status_id") or "")
        # в списке показываем имена; если есть - поставим как текстом (даже если нет в выпадающем)
        if self._order.get("status_id") is not None:
            pass

        # status_name / pp_name проще восстановить из списка заказов, но здесь подставим по тексту при наличии
        if "status_name" in self._order and self._order["status_name"]:
            self.ui.status_combo.setCurrentText(str(self._order["status_name"]))
        if "pp_name" in self._order and self._order["pp_name"]:
            self.ui.pickup_combo.setCurrentText(str(self._order["pp_name"]))

        od = self._order.get("order_date")
        if isinstance(od, date):
            self.ui.order_date_edit.setDate(QDate(od.year, od.month, od.day))

        dd = self._order.get("order_pup_date")
        if isinstance(dd, date):
            self.ui.delivery_date_edit.setDate(QDate(dd.year, dd.month, dd.day))

        items = self._order.get("items") or []
        if items:
            txt = ", ".join([f"{x['art']}, {x['qty']}" for x in items])
            self.ui.article_edit.setPlainText(txt)

    def _save(self):
        try:
            oid = None
            if self.ui.id_edit.text().strip():
                oid = int(self.ui.id_edit.text().strip())

            od_q = self.ui.order_date_edit.date()
            dd_q = self.ui.delivery_date_edit.date()
            od = date(od_q.year(), od_q.month(), od_q.day())
            dd = date(dd_q.year(), dd_q.month(), dd_q.day()) if dd_q.isValid() else None

            saved_id = upsert_order(
                order_id=oid,
                status_name=self.ui.status_combo.currentText().strip() or None,
                pickup_address=self.ui.pickup_combo.currentText().strip() or None,
                order_date=od,
                delivery_date=dd,
                receiver_code=self.ui.receiver_edit.text(),
                client_name=self.ui.client_edit.text(),
                items_text=self.ui.article_edit.toPlainText(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return
        self._on_saved(saved_id)
        self.accept()

