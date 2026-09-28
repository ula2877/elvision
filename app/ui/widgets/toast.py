from __future__ import annotations

import time
from typing import Optional
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect


@dataclass
class NotificationType:
    key: str
    label: str
    icon: str
    color: str

    @staticmethod
    def fall_detection() -> NotificationType:
        return NotificationType("fall_detection", "Fall Detection", "\u26a0", "#DC2626")

    @staticmethod
    def restricted_area() -> NotificationType:
        return NotificationType("restricted_area", "Restricted Area", "\ud83d\udea8", "#F59E0B")

    @staticmethod
    def smoke() -> NotificationType:
        return NotificationType("smoke", "Smoke Detected", "\ud83d\udd25", "#F97316")

    @staticmethod
    def fire() -> NotificationType:
        return NotificationType("fire", "Fire Detected", "\ud83d\udd25", "#EF4444")

    @staticmethod
    def ppe() -> NotificationType:
        return NotificationType("ppe", "PPE Violation", "\ud83d\udee1\ufe0f", "#8B5CF6")

    @staticmethod
    def connection_lost() -> NotificationType:
        return NotificationType("connection_lost", "Connection Lost", "\u26a0", "#6B7280")

    @staticmethod
    def system() -> NotificationType:
        return NotificationType("system", "System", "\u2139\ufe0f", "#3B82F6")


_TOAST_WIDTH = 320
_TOAST_DURATION_MS = 5000
_ANIM_DURATION_MS = 300


class ToastWidget(QWidget):
    closed = Signal(object)  # ToastWidget
    clicked = Signal(str)    # camera_id

    def __init__(
        self,
        camera_id: str,
        title: str,
        subtitle: str,
        notif_type: NotificationType,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._camera_id = camera_id
        self._type = notif_type

        self.setFixedWidth(_TOAST_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background-color: rgba(15, 15, 25, 230); border-radius: 8px; "
            f"border-left: 2px solid {notif_type.color};"
        )
        self.setVisible(False)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 14, 10)
        root.setSpacing(10)

        icon_label = QLabel(notif_type.icon)
        icon_label.setStyleSheet(f"font-size: 18px; background: transparent; color: {notif_type.color}; border-left: none;")
        icon_label.setFixedWidth(24)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #F1F5F9; font-size: 12px; font-weight: 700; background: transparent; border-left: none;")
        title_label.setWordWrap(True)
        text_col.addWidget(title_label)

        meta = QHBoxLayout()
        meta.setSpacing(8)

        type_label = QLabel(notif_type.label)
        type_label.setStyleSheet(f"color: {notif_type.color}; font-size: 10px; font-weight: 600; background: transparent; border-left: none;")
        meta.addWidget(type_label)

        time_label = QLabel(time.strftime("%H:%M:%S"))
        time_label.setStyleSheet("color: #64748B; font-size: 10px; background: transparent; border-left: none;")
        meta.addWidget(time_label)

        meta.addStretch()
        text_col.addLayout(meta)

        root.addLayout(text_col)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(_ANIM_DURATION_MS)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(_ANIM_DURATION_MS)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._close_fade = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._close_fade.setDuration(250)
        self._close_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._close_fade.finished.connect(self._on_close_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.start_close)

        self._closing = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._closing:
            self.clicked.emit(self._camera_id)
            event.accept()
        else:
            super().mousePressEvent(event)

    def show_animated(self, target_pos: QPoint) -> None:
        start_x = self.parent().width() + 50
        self.move(start_x, target_pos.y())
        self.setVisible(True)
        self.raise_()

        self._slide_anim.stop()
        self._slide_anim.setStartValue(self.pos())
        self._slide_anim.setEndValue(target_pos)
        self._slide_anim.start()

        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self._timer.start(_TOAST_DURATION_MS)

    def animate_to(self, target_pos: QPoint) -> None:
        if self._closing:
            return
        self._slide_anim.stop()
        self._slide_anim.setStartValue(self.pos())
        self._slide_anim.setEndValue(target_pos)
        self._slide_anim.start()

    def start_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._slide_anim.stop()
        self._close_fade.stop()
        self._close_fade.setStartValue(self._opacity_effect.opacity())
        self._close_fade.setEndValue(0.0)
        self._close_fade.start()

    def is_closing(self) -> bool:
        return self._closing

    def _on_close_finished(self) -> None:
        self.closed.emit(self)
        self.deleteLater()
