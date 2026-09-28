"""
StatusBar — bottom status bar with camera count, connection info, and clock.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QFrame,
)

from app.models import CameraStatus


class StatusBar(QWidget):
    """Bottom status bar."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(28)
        self._build_ui()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        self._camera_count_label = QLabel("0 cameras")
        self._camera_count_label.setStyleSheet("color: #8892A4; font-size: 11px;")
        layout.addWidget(self._camera_count_label)

        self._online_label = QLabel("0 online")
        self._online_label.setStyleSheet("color: #22C55E; font-size: 11px;")
        layout.addWidget(self._online_label)

        self._offline_label = QLabel("0 offline")
        self._offline_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        layout.addWidget(self._offline_label)

        layout.addStretch()

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #8892A4; font-size: 11px;")
        layout.addWidget(self._status_label)

        self._clock_label = QLabel()
        self._clock_label.setStyleSheet("color: #8892A4; font-size: 11px;")
        layout.addWidget(self._clock_label)

    def update_counts(
        self, total: int, online: int, offline: int, error: int = 0
    ) -> None:
        self._camera_count_label.setText(f"{total} camera{'s' if total != 1 else ''}")
        self._online_label.setText(f"{online} online")
        self._offline_label.setText(f"{offline + error} offline")

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _update_clock(self) -> None:
        self._clock_label.setText(time.strftime("%H:%M:%S"))
