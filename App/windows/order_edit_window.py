from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QMessageBox, QSizePolicy, QVBoxLayout

from App.order_service import list_pickup_points, list_statuses, upsert_order
from App.paths import ui_path
from App.ui_loader import load_ui


class OrderEditWindow(QDialog):
    def __init__(
        self,
        *,
        order: dict | None,
        is_admin: bool,
        on_saved,
        default_client_name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._order = order
        self._is_admin = is_admin
        self._on_saved = on_saved
        self._default_client_name = (default_client_name or "").strip()

        self.ui = load_ui(ui_path("order_form.ui"))
        self.setWindowTitle(self.ui.windowTitle() if order is not None else "Новый заказ")
        self.setMinimumSize(self.ui.minimumSize())
        self.resize(740, 600)
        self._tune_form_layout()
        if is_admin:
            self.ui.status_combo.setEditable(True)
            self.ui.pickup_combo.setEditable(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)

        self.ui.btn_cancel.clicked.connect(self.reject)
        self.ui.btn_save.clicked.connect(self._save)

        self._fill_lists()
        self._load_data()

        if not is_admin:
            self.setWindowTitle("Просмотр заказа")
            self._set_read_only()

    def _tune_form_layout(self):
        for fl in (self.ui.formLayout, self.ui.right_form):
            fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            fl.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            fl.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            fl.setHorizontalSpacing(14)
            fl.setVerticalSpacing(10)
        for lbl in (
            self.ui.lbl_id,
            self.ui.lbl_article,
            self.ui.lbl_status,
            self.ui.lbl_pickup,
            self.ui.lbl_order_date,
            self.ui.lbl_receiver,
            self.ui.lbl_client,
            self.ui.lbl_delivery,
        ):
            lbl.setMinimumWidth(170)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.ui.pickup_combo.setMinimumWidth(380)
        self.ui.client_edit.setMinimumWidth(380)
        self.ui.status_combo.setMinimumWidth(220)
        self.ui.article_edit.setMinimumHeight(88)

    def _set_read_only(self):
        self.ui.btn_save.setEnabled(False)
        for w in [
            self.ui.article_edit,
            self.ui.status_combo,
            self.ui.pickup_combo,
            self.ui.order_date_edit,
            self.ui.delivery_date_edit,
            self.ui.receiver_edit,
            self.ui.client_edit,
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
            self.ui.lbl_id.setVisible(False)
            self.ui.id_edit.setVisible(False)
            self.ui.id_edit.setText("")
            self.ui.client_edit.setText(self._default_client_name or "")
            self.ui.order_date_edit.setDate(QDate.currentDate())
            self.ui.delivery_date_edit.setDate(QDate.currentDate())
            return

        self.ui.lbl_id.setVisible(True)
        self.ui.id_edit.setVisible(True)
        self.ui.id_edit.setReadOnly(True)
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
            # Новый заказ — без ID; редактирование — ID существующей записи
            oid = None if self._order is None else int(self._order["order_id"])

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

