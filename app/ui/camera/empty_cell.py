"""
EmptyCameraCell — styled placeholder for unoccupied grid slots.
Displays "+" and "No Camera" perfectly centered.
Uses manual geometry to guarantee visual centering regardless of layout.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPen, QPainter
from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy


class EmptyCameraCell(QWidget):
    """Placeholder cell for an unoccupied grid slot.

    Always has identical dimensions to CameraWidget.
    Size is set externally by Workspace via setFixedSize.
    Uses manual geometry to center the "+" icon and "No Camera" text.
    """

    add_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyCameraCell")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )

        self._icon_label = QLabel("+", self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            "font-size: 36px; font-weight: 300; color: #3A3D4A; "
            "background: transparent; border: none;"
        )

        self._text_label = QLabel("No Camera", self)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setStyleSheet(
            "font-size: 12px; color: #4B5060; font-weight: 500; "
            "background: transparent; border: none;"
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        icon_h = 40
        text_h = 16
        spacing = 8
        total = icon_h + spacing + text_h
        start_y = (h - total) // 2
        self._icon_label.setGeometry(0, start_y, w, icon_h)
        self._text_label.setGeometry(0, start_y + icon_h + spacing, w, text_h)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = "#3B82F6" if self._hovered else "#1E2028"
        bg = "#12141C" if self._hovered else "#0A0C10"

        p.setBrush(QColor(bg))
        p.setPen(QPen(QColor(border_color), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        p.end()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._icon_label.setStyleSheet(
            "font-size: 36px; font-weight: 300; color: #3B82F6; "
            "background: transparent; border: none;"
        )
        self._text_label.setStyleSheet(
            "font-size: 12px; color: #8892A4; font-weight: 500; "
            "background: transparent; border: none;"
        )
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._icon_label.setStyleSheet(
            "font-size: 36px; font-weight: 300; color: #3A3D4A; "
            "background: transparent; border: none;"
        )
        self._text_label.setStyleSheet(
            "font-size: 12px; color: #4B5060; font-weight: 500; "
            "background: transparent; border: none;"
        )
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.add_requested.emit()
