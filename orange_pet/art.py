"""Artwork entry points used by the app, tray and settings panel."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from .characters import CHARACTERS, draw_cat


def character_icon(key="cat", size=128):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    CHARACTERS[key][1](painter, QRectF(0, 0, size, size), frame=1)
    painter.end()
    return QIcon(pixmap)


def app_icon() -> QIcon:
    return character_icon()
