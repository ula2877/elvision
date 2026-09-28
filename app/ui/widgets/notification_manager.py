from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QObject, QPoint, Signal
from PySide6.QtWidgets import QWidget

from app.ui.widgets.toast import ToastWidget, NotificationType

_TOP_MARGIN = 60
_RIGHT_MARGIN = 20
_TOAST_SPACING = 10
_TOAST_WIDTH = 320
_MAX_VISIBLE = 5


class NotificationManager(QObject):
    toast_clicked = Signal(str)  # camera_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._toasts: list[ToastWidget] = []

    @property
    def _anchor(self) -> QWidget:
        p = self.parent()
        if isinstance(p, QWidget):
            return p
        raise TypeError("NotificationManager parent must be a QWidget")

    def show_notification(
        self,
        camera_id: str,
        title: str,
        subtitle: str = "",
        notif_type: Optional[NotificationType] = None,
    ) -> None:
        if notif_type is None:
            notif_type = NotificationType.fall_detection()
        if len(self._toasts) >= _MAX_VISIBLE:
            oldest = self._toasts[0]
            if not oldest.is_closing():
                oldest.start_close()

        toast = ToastWidget(camera_id, title, subtitle, notif_type, self._anchor)
        toast.closed.connect(self._on_toast_closed)
        toast.clicked.connect(self.toast_clicked.emit)
        toast.adjustSize()
        self._toasts.append(toast)

        target = self._compute_position(len(self._toasts) - 1)
        toast.show_animated(target)

    def _compute_position(self, index: int) -> QPoint:
        anchor = self._anchor
        x = anchor.width() - _TOAST_WIDTH - _RIGHT_MARGIN
        y = _TOP_MARGIN
        for i in range(index):
            prev = self._toasts[i]
            y += prev.height() + _TOAST_SPACING
        return QPoint(max(x, 0), y)

    def _on_toast_closed(self, toast: ToastWidget) -> None:
        try:
            self._toasts.remove(toast)
        except ValueError:
            pass
        self._relayout()

    def _relayout(self) -> None:
        for i, toast in enumerate(self._toasts):
            target = self._compute_position(i)
            toast.animate_to(target)
