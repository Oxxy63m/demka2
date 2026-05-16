from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtWidgets import QPushButton, QWidget


class CardClickFilter(QObject):
    def __init__(self, on_click: Callable[[], None], parent: QWidget):
        super().__init__(parent)
        self._on_click = on_click

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._on_click()
        return True


def install_card_click(card: QWidget, on_click: Callable[[], None]) -> None:
    """Клик по карточке (как по товару). Работает с виджетами из .ui."""
    for w in card.findChildren(QWidget):
        if isinstance(w, QPushButton):
            continue
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    card.setCursor(Qt.CursorShape.PointingHandCursor)
    card.installEventFilter(CardClickFilter(on_click, parent=card))
