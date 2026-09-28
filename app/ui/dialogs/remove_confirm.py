"""
RemoveConfirmDialog — confirmation dialog for batch camera removal.

Displays the list of cameras about to be removed with a clear warning.
Default action is Cancel (safe default).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
)

from app.models import CameraInfo, CameraStatus


_STATUS_ICONS: dict[CameraStatus, str] = {
    CameraStatus.ONLINE: "\u25CF",    # ●
    CameraStatus.OFFLINE: "\u25CB",   # ○
    CameraStatus.CONNECTING: "\u25CC",# ◌
    CameraStatus.ERROR: "\u2716",     # ✖
    CameraStatus.BUFFERING: "\u25D4", # ◔
    CameraStatus.DISCONNECTED: "\u2716",
    CameraStatus.PAUSED: "\u25AE",    # ▮
}


class RemoveConfirmDialog(QDialog):
    """Modal confirmation dialog for camera removal.

    Shows:
        - Title
        - List of cameras to remove (with status icons)
        - Warning text
        - Cancel / Remove buttons (Cancel is default)
    """

    def __init__(
        self,
        cameras: list[tuple[CameraInfo, CameraStatus]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Remove Cameras")
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
        self.setMinimumHeight(300)
        self.setModal(True)
        self._cameras = cameras
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1A1D27; }"
            "QLabel { color: #E2E8F0; font-size: 12px; background: transparent; }"
            "QPushButton#danger { background-color: #EF4444; color: white; "
            "border: none; border-radius: 6px; padding: 8px 24px; font-weight: 600; "
            "font-size: 12px; }"
            "QPushButton#danger:hover { background-color: #DC2626; }"
            "QPushButton#cancel { background: transparent; border: 1px solid #2E3140; "
            "color: #8892A4; border-radius: 6px; padding: 8px 24px; font-size: 12px; }"
            "QPushButton#cancel:hover { border-color: #E2E8F0; color: #E2E8F0; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Title ───────────────────────────────────────
        title = QLabel("Remove Cameras")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #E2E8F0; background: transparent;"
        )
        root.addWidget(title)

        # ── Count ───────────────────────────────────────
        count = len(self._cameras)
        count_text = (
            "You are about to remove %d camera%s:"
            % (count, "s" if count != 1 else "")
        )
        count_label = QLabel(count_text)
        count_label.setStyleSheet(
            "color: #8892A4; font-size: 12px; background: transparent;"
        )
        root.addWidget(count_label)

        # ── Camera list ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #2E3140; border-radius: 6px; "
            "background: #21242F; }"
        )

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(12, 8, 12, 8)
        list_layout.setSpacing(4)

        for info, status in self._cameras:
            icon = _STATUS_ICONS.get(status, "\u25CB")
            status_color = {
                CameraStatus.ONLINE: "#22C55E",
                CameraStatus.OFFLINE: "#6B7280",
                CameraStatus.CONNECTING: "#3B82F6",
                CameraStatus.ERROR: "#EF4444",
                CameraStatus.BUFFERING: "#F59E0B",
                CameraStatus.DISCONNECTED: "#EF4444",
                CameraStatus.PAUSED: "#8B5CF6",
            }.get(status, "#6B7280")

            row = QLabel(
                '  <span style="color: %s; font-size: 12px;">%s</span>  '
                '<span style="color: #E2E8F0; font-size: 12px; font-weight: 500;">%s</span>  '
                '<span style="color: #8892A4; font-size: 10px;">%s</span>'
                % (status_color, icon, info.name, info.source_type.display_name)
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setFixedHeight(28)
            list_layout.addWidget(row)

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        root.addWidget(scroll, 1)

        # ── Warning ─────────────────────────────────────
        warning = QLabel(
            "This will stop all streams and release associated resources."
        )
        warning.setStyleSheet(
            "color: #F59E0B; font-size: 11px; font-style: italic; background: transparent;"
        )
        root.addWidget(warning)

        # ── Buttons ─────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("danger")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self.accept)
        btn_layout.addWidget(remove_btn)

        root.addLayout(btn_layout)
