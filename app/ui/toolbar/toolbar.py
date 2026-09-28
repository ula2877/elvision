"""
Toolbar — top action bar with layout selector and utilities.
Reads layout state from LayoutManager (single source of truth).
Emits layout_changed when user selects a different grid.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QComboBox,
    QSizePolicy,
)

from app.core.layout.manager import LayoutManager
from app.models import LayoutGrid


class Toolbar(QWidget):
    """Top toolbar with layout selector and utilities.

    Layout flow:
    - Toolbar READS from LayoutManager (via constructor reference)
    - Toolbar EMITS layout_changed(str) when user changes combo
    - MainWindow forwards to LayoutManager.set_grid()
    - LayoutManager emits layout_changed → Workspace rebuilds
    """

    settings_requested = Signal()
    snapshot_requested = Signal()
    record_requested = Signal()
    layout_changed = Signal(str)  # LayoutGrid.name — user changed the combo
    refresh_requested = Signal()
    fullscreen_requested = Signal()
    event_center_requested = Signal()

    def __init__(
        self,
        layout_manager: LayoutManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        self._layout_manager = layout_manager
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setFixedHeight(48)
        self._build_ui()
        self._sync_from_manager()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        app_label = QLabel("Elvision")
        app_label.setStyleSheet(
            "color: #3B82F6; font-size: 16px; font-weight: 700; padding: 0 8px;"
        )
        layout.addWidget(app_label)

        sep1 = self._separator()
        layout.addWidget(sep1)

        layout_label = QLabel("Layout:")
        layout_label.setStyleSheet("color: #8892A4; font-size: 12px; padding-left: 4px;")
        layout.addWidget(layout_label)

        self._layout_combo = QComboBox()
        self._layout_combo.setFixedWidth(100)
        for grid in LayoutGrid:
            if grid != LayoutGrid.CUSTOM:
                self._layout_combo.addItem(grid.name.replace("GRID_", ""), grid.name)
        self._layout_combo.currentTextChanged.connect(self._on_combo_changed)
        layout.addWidget(self._layout_combo)

        sep2 = self._separator()
        layout.addWidget(sep2)

        self._refresh_btn = self._make_button("Refresh", "Refresh All")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

        self._fullscreen_btn = self._make_button("Fullscreen", "Toggle Fullscreen")
        self._fullscreen_btn.clicked.connect(self.fullscreen_requested.emit)
        layout.addWidget(self._fullscreen_btn)

        layout.addStretch()

        self._events_btn = self._make_icon_button("E", "Event Center")
        self._events_btn.clicked.connect(self.event_center_requested.emit)
        layout.addWidget(self._events_btn)

    def _on_combo_changed(self, text: str) -> None:
        grid_name = self._layout_combo.currentData()
        if grid_name:
            self.layout_changed.emit(grid_name)

    def _sync_from_manager(self) -> None:
        """Read the current grid from LayoutManager and update the combo.
        Blocks signals to prevent emitting layout_changed during init."""
        self._layout_combo.blockSignals(True)
        grid_name = self._layout_manager.current_grid.name
        idx = self._layout_combo.findData(grid_name)
        if idx >= 0:
            self._layout_combo.setCurrentIndex(idx)
        self._layout_combo.blockSignals(False)

    def set_fullscreen_active(self, active: bool) -> None:
        if active:
            self._fullscreen_btn.setStyleSheet(
                "QPushButton { background: #3B82F6; border: none; color: #FFFFFF; "
                "padding: 4px 10px; border-radius: 4px; font-size: 12px; } "
                "QPushButton:hover { background: #2563EB; }"
            )
        else:
            self._fullscreen_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; color: #E2E8F0; "
                "padding: 4px 10px; border-radius: 4px; font-size: 12px; } "
                "QPushButton:hover { background: #2A2D3A; } "
                "QPushButton:pressed { background: #3B82F6; }"
            )

    def _make_button(self, text: str, tooltip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("iconButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #E2E8F0; "
            "padding: 4px 10px; border-radius: 4px; font-size: 12px; } "
            "QPushButton:hover { background: #2A2D3A; } "
            "QPushButton:pressed { background: #3B82F6; }"
        )
        return btn

    def _make_icon_button(self, icon_text: str, tooltip: str = "") -> QPushButton:
        btn = QPushButton(icon_text)
        btn.setObjectName("iconButton")
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #2E3140; "
            "color: #8892A4; border-radius: 16px; font-size: 12px; font-weight: bold; } "
            "QPushButton:hover { background: #2A2D3A; color: #E2E8F0; border-color: #3B82F6; }"
        )
        return btn

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(24)
        sep.setStyleSheet("color: #2E3140;")
        return sep
