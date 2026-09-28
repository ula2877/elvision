"""
CameraWidget — passive camera display container.

Contains VideoRenderer + overlays + floating toolbar.
Never resizes itself. Geometry is controlled exclusively by LayoutManager.
Uses manual geometry (no QLayout) to guarantee VideoRenderer fills the full viewport.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import QWidget, QFrame, QSizePolicy

from app.ui.camera.video_surface import VideoRenderer
from app.ui.camera.floating_toolbar import FloatingToolbar
from app.models import CameraInfo, CameraStatus, DisplayMode


class CameraWidget(QFrame):
    """Passive camera display container.

    Contains:
    - VideoRenderer (video rendering, fills entire widget)
    - Top-left overlay (name, status)
    - Bottom overlay (FPS, resolution, timestamp)
    - Floating toolbar (on hover)

    Geometry rules:
    - CameraWidget size is set by Workspace via QGridLayout cell constraints
    - VideoRenderer fills the ENTIAL CameraWidget via setGeometry in resizeEvent
    - No QLayout is used — manual geometry guarantees pixel-perfect fill
    - No child widget may request a larger or smaller size
    """

    _RENDER_FPS_LIMIT = 10

    snapshot_requested = Signal(str)
    record_requested = Signal(str)
    fullscreen_requested = Signal(str)
    reconnect_requested = Signal(str)
    settings_requested = Signal(str)

    def __init__(
        self,
        camera_info: Optional[CameraInfo] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._camera_info = camera_info
        self._status = CameraStatus.OFFLINE
        self._fps: float = 0.0
        self._resolution: str = ""
        self._timestamp: float = 0.0
        self._is_recording: bool = False
        self._render_frame_count = 0
        self._last_render_time = 0.0
        self._render_interval = 1.0 / self._RENDER_FPS_LIMIT
        self._alarm_active: bool = False
        self._blink_visible: bool = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self.setObjectName("cameraWidget")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._default_style = (
            "QFrame#cameraWidget { background-color: #0A0C10; border-radius: 6px; "
            "border: 1px solid #2E3140; } "
            "QFrame#cameraWidget:hover { border-color: #3B82F6; }"
        )
        self.setStyleSheet(self._default_style)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )

        self._build_ui()

    def _build_ui(self) -> None:
        self._video_renderer = VideoRenderer(self)

        self._floating_toolbar = FloatingToolbar(self)
        self._floating_toolbar.hide()
        self._floating_toolbar.fullscreen_requested.connect(
            lambda: self.fullscreen_requested.emit(self._camera_id)
        )
        self._floating_toolbar.reconnect_requested.connect(
            lambda: self.reconnect_requested.emit(self._camera_id)
        )
        self._floating_toolbar.settings_requested.connect(
            lambda: self.settings_requested.emit(self._camera_id)
        )

        self._video_renderer.show_idle()

    @property
    def _camera_id(self) -> str:
        return self._camera_info.id if self._camera_info else ""

    @property
    def display_mode(self) -> DisplayMode:
        return self._video_renderer.display_mode

    @display_mode.setter
    def display_mode(self, mode: DisplayMode) -> None:
        self._video_renderer.display_mode = mode

    def set_camera_info(self, info: CameraInfo) -> None:
        self._camera_info = info
        self._resolution = f"{info.width}x{info.height}"

    def update_frame(self, frame_data: object) -> None:
        from app.models import FrameData

        if not isinstance(frame_data, FrameData):
            return
        if frame_data.camera_id != self._camera_id:
            return

        self._fps = frame_data.fps
        self._timestamp = frame_data.timestamp
        self._resolution = f"{frame_data.width}x{frame_data.height}"

        now = time.time()
        if now - self._last_render_time < self._render_interval:
            return
        self._last_render_time = now

        self._video_renderer.update_frame(frame_data.data)
        self.update()

    def set_status(self, status: CameraStatus) -> None:
        self._status = status
        if status == CameraStatus.OFFLINE:
            self._video_renderer.show_idle()
        elif status == CameraStatus.CONNECTING:
            self._video_renderer.show_connecting()
        elif status == CameraStatus.ERROR:
            self._video_renderer.show_error("ERROR")
        self.update()

    def set_alarm(self, active: bool) -> None:
        self._alarm_active = active
        if active:
            self._blink_visible = True
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink_visible = False
        self._apply_alarm_style()

    def _toggle_blink(self) -> None:
        self._blink_visible = not self._blink_visible
        self._apply_alarm_style()

    def _apply_alarm_style(self) -> None:
        if self._alarm_active and self._blink_visible:
            self.setStyleSheet(
                "QFrame#cameraWidget { background-color: #0A0C10; border-radius: 6px; "
                "border: 3px solid #EF4444; } "
                "QFrame#cameraWidget:hover { border-color: #EF4444; }"
            )
        else:
            self.setStyleSheet(self._default_style)

    def set_recording(self, recording: bool) -> None:
        self._is_recording = recording
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_top_overlay(painter)
        self._paint_bottom_overlay(painter)
        if self._is_recording:
            self._paint_recording_indicator(painter)
        painter.end()

    def _paint_top_overlay(self, p: QPainter) -> None:
        w = self.width()
        name = self._camera_info.name if self._camera_info else "Unknown"
        status_text = self._status.value.upper()

        gradient_height = 40
        overlay = QColor(0, 0, 0, 160)
        p.fillRect(0, 0, w, gradient_height, overlay)

        p.setPen(QPen(QColor("#E2E8F0")))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(8, 4, w - 16, gradient_height, Qt.AlignmentFlag.AlignVCenter, name)

        status_color = {
            CameraStatus.ONLINE: QColor("#22C55E"),
            CameraStatus.OFFLINE: QColor("#6B7280"),
            CameraStatus.CONNECTING: QColor("#3B82F6"),
            CameraStatus.ERROR: QColor("#EF4444"),
            CameraStatus.BUFFERING: QColor("#F59E0B"),
            CameraStatus.DISCONNECTED: QColor("#EF4444"),
        }.get(self._status, QColor("#6B7280"))

        p.setPen(QPen(status_color))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(8, gradient_height - 2, 100, 14, Qt.AlignmentFlag.AlignBottom, status_text)

    def _paint_bottom_overlay(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        gradient_height = 28
        overlay = QColor(0, 0, 0, 140)
        p.fillRect(0, h - gradient_height, w, gradient_height, overlay)

        ts_str = time.strftime("%Y-%m-%d %H:%M:%S") if self._timestamp else "--:--:--"
        fps_str = f"{self._fps:.1f} FPS" if self._fps else "0 FPS"
        res_str = self._resolution or "--x--"

        info = f"{fps_str}  |  {res_str}  |  {ts_str}"
        p.setPen(QPen(QColor("#8892A4")))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(
            0, h - gradient_height, w, gradient_height,
            Qt.AlignmentFlag.AlignCenter, info,
        )

    def _paint_recording_indicator(self, p: QPainter) -> None:
        x, y = self.width() - 24, 10
        p.setBrush(QBrush(QColor("#EF4444")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(x, y, 12, 12)
        p.setPen(QPen(QColor("#FFFFFF")))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(x, y, 12, 12, Qt.AlignmentFlag.AlignCenter, "R")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._video_renderer.setGeometry(0, 0, w, h)
        self._floating_toolbar.setGeometry(
            (w - 260) // 2,
            h - 48,
            260,
            36,
        )

    def enterEvent(self, event) -> None:
        self._floating_toolbar.show_smooth()

    def leaveEvent(self, event) -> None:
        self._floating_toolbar.hide_smooth()
