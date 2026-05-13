from __future__ import annotations

from PySide6.QtCore import QFile, QObject
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget


def _bind_children_as_attrs(root: QWidget) -> None:
    # QUiLoader не создаёт Python-атрибуты для дочерних объектов.
    # Ищем все QObject с objectName — включая QLayout (cards_layout, verticalLayout и т.д.).
    for ch in root.findChildren(QObject):
        name = ch.objectName()
        if not name:
            continue
        if hasattr(root, name):
            continue
        try:
            setattr(root, name, ch)
        except Exception:
            pass


def load_ui(ui_file_path: str) -> QWidget:
    f = QFile(ui_file_path)
    if not f.open(QFile.ReadOnly):
        raise RuntimeError(f"Не удалось открыть UI-файл: {ui_file_path}")
    try:
        loader = QUiLoader()
        w = loader.load(f)
        if w is None:
            raise RuntimeError(f"Не удалось загрузить UI: {ui_file_path}")
        _bind_children_as_attrs(w)
        return w
    finally:
        f.close()

