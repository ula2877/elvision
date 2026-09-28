"""
FloatingToolbar — appears on hover over a CameraWidget.
Smooth opacity animation. Auto-hide after delay.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Property,
    Signal,
)
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QGraphicsOpacityEffect,
)


class FloatingToolbar(QWidget):
    """Transparent floating toolbar that appears on hover."""

    fullscreen_requested = Signal()
    reconnect_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFixedHeight(36)
        self.setStyleSheet("background: rgba(15, 17, 23, 210); border-radius: 6px;")

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(150)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(2500)
        self._hide_timer.timeout.connect(self.hide_smooth)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(2)

        buttons = [
            ("Fullscreen", self.fullscreen_requested),
            ("Reconnect", self.reconnect_requested),
            ("Settings", self.settings_requested),
        ]
        for label, signal in buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; "
                "color: #E2E8F0; padding: 0 8px; border-radius: 4px; font-size: 11px; } "
                "QPushButton:hover { background: rgba(59,130,246,0.3); }"
            )
            btn.clicked.connect(signal.emit)
            layout.addWidget(btn)

    def show_smooth(self) -> None:
        self._hide_timer.stop()
        self.show()
        self._fade_out.stop()
        self._fade_in.start()
        self._hide_timer.start()

    def hide_smooth(self) -> None:
        self._fade_in.stop()
        self._fade_out.start()
        self._fade_out.finished.connect(self._on_hide_done)

    def _on_hide_done(self) -> None:
        self._fade_out.finished.disconnect(self._on_hide_done)
        self.hide()

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()

    def leaveEvent(self, event) -> None:
        self._hide_timer.start()
