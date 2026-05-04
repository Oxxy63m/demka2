from __future__ import annotations

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget


def _bind_children_as_attrs(root: QWidget) -> None:
    # QUiLoader не создаёт Python-атрибуты для дочерних виджетов.
    # Для простого учебного проекта удобно "пробиндить" их по objectName.
    for ch in root.findChildren(QWidget):
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

