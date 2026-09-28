"""
VideoRenderer — production-grade video rendering widget.

Uses QPainter for frame display. Never changes its own size.
All sizing is controlled by the parent layout (LayoutManager → Workspace → CameraWidget).
Supports FIT, FILL, and STRETCH display modes.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget

from app.models import DisplayMode


class VideoRenderer(QWidget):
    """Renders video frames inside a fixed-size cell.

    Architecture:
    - Receives numpy BGR frames from CameraWidget
    - Converts to QPixmap once (cached)
    - Paints via QPainter in paintEvent using the selected display mode
    - Never calls setPixmap or changes its own sizeHint
    - Size is entirely determined by the parent layout grid
    """

    display_mode_changed = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._current_frame: Optional[np.ndarray] = None
        self._pixmap: Optional[QPixmap] = None
        self._rgb_buffer: Optional[np.ndarray] = None
        self._aspect_ratio: float = 16 / 9
        self._display_mode: DisplayMode = DisplayMode.FIT
        self._bg_color = QColor("#0A0C10")
        self._scaled_pixmap: Optional[QPixmap] = None
        self._scaled_size: tuple = (0, 0)

    @property
    def display_mode(self) -> DisplayMode:
        return self._display_mode

    @display_mode.setter
    def display_mode(self, mode: DisplayMode) -> None:
        if mode != self._display_mode:
            self._display_mode = mode
            self.update()
            self.display_mode_changed.emit(mode)

    def update_frame(self, frame: np.ndarray) -> None:
        """Accept a new BGR frame and cache it as QPixmap.
        Does NOT resize the widget. Only triggers a repaint.
        """
        self._current_frame = frame
        h, w = frame.shape[:2]
        if h > 0 and w > 0:
            self._aspect_ratio = w / h

        if self._rgb_buffer is None or self._rgb_buffer.shape[:2] != (h, w):
            self._rgb_buffer = np.empty((h, w, 3), dtype=np.uint8)
        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buffer)
        ch = self._rgb_buffer.shape[2]
        bytes_per_line = ch * self._rgb_buffer.shape[1]
        qimg = QImage(self._rgb_buffer.data, self._rgb_buffer.shape[1], self._rgb_buffer.shape[0], bytes_per_line, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._scaled_pixmap = None
        self._scaled_size = (0, 0)
        self.update()

    def show_idle(self) -> None:
        self._pixmap = None
        self._current_frame = None
        self._rgb_buffer = None
        self._scaled_pixmap = None
        self._scaled_size = (0, 0)
        self._draw_placeholder("NO SIGNAL", "#3A3D4A")
        self.update()

    def show_connecting(self) -> None:
        self._pixmap = None
        self._current_frame = None
        self._rgb_buffer = None
        self._scaled_pixmap = None
        self._scaled_size = (0, 0)
        self._draw_placeholder("CONNECTING...", "#2563EB")
        self.update()

    def show_error(self, message: str = "ERROR") -> None:
        self._pixmap = None
        self._current_frame = None
        self._rgb_buffer = None
        self._scaled_pixmap = None
        self._scaled_size = (0, 0)
        self._draw_placeholder(message, "#991B1B")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, self._bg_color)

        if self._pixmap is not None and not self._pixmap.isNull():
            self._paint_frame(p, w, h)
        else:
            self._paint_placeholder_text(p, w, h)

        p.end()

    def _paint_frame(self, p: QPainter, w: int, h: int) -> None:
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw <= 0 or ph <= 0:
            return

        if self._display_mode == DisplayMode.STRETCH:
            p.drawPixmap(0, 0, w, h, self._pixmap)

        elif self._display_mode == DisplayMode.FILL:
            frame_ar = pw / ph
            cell_ar = w / h
            if frame_ar > cell_ar:
                draw_h = h
                draw_w = int(h * frame_ar)
            else:
                draw_w = w
                draw_h = int(w / frame_ar)
            x = (w - draw_w) // 2
            y = (h - draw_h) // 2
            p.drawPixmap(x, y, draw_w, draw_h, self._pixmap)

        else:  # FIT (default)
            if self._scaled_pixmap is None or self._scaled_size != (w, h):
                self._scaled_pixmap = self._pixmap.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._scaled_size = (w, h)
            x = (w - self._scaled_pixmap.width()) // 2
            y = (h - self._scaled_pixmap.height()) // 2
            p.drawPixmap(x, y, self._scaled_pixmap)

    def _draw_placeholder(self, text: str, bg_color: str) -> None:
        self._placeholder_text = text
        self._placeholder_bg = bg_color
        self.update()

    def _paint_placeholder_text(self, p: QPainter, w: int, h: int) -> None:
        text = getattr(self, "_placeholder_text", "NO SIGNAL")
        bg = getattr(self, "_placeholder_bg", "#3A3D4A")
        p.fillRect(0, 0, w, h, QColor(bg))
        p.setPen(QPen(QColor("#E2E8F0")))
        font = QFont("Segoe UI", max(10, min(w // 14, 18)))
        font.setBold(True)
        p.setFont(font)
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, text)
