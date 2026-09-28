"""
Workspace — center camera grid workspace.

Receives LayoutManager from MainWindow (single source of truth).
Enforces uniform cell dimensions on every CameraWidget and EmptyCameraCell.

Architecture:
  LayoutManager.cell_size() → Workspace → setFixedSize(widget, cell_size)
  CameraWidget never resizes itself. VideoRenderer adapts to the cell.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QWidget, QGridLayout, QStackedLayout, QLabel

from app.core.layout.manager import LayoutManager
from app.ui.camera.camera_widget import CameraWidget
from app.ui.camera.empty_cell import EmptyCameraCell
from app.models import CameraInfo, CameraStatus, FrameData, LayoutGrid


class Workspace(QWidget):
    """Center camera grid workspace.

    Guarantees:
    - Grid always matches selected layout (rows×cols cells)
    - Every cell has identical dimensions (enforced via setFixedSize)
    - CameraWidgets are reused across layout switches
    - Empty slots show EmptyCameraCell with identical dimensions
    - Fullscreen: double-click isolates camera, ESC restores
    - Group filtering: only filtered cameras displayed when active
    """

    camera_snapshot_requested = Signal(str)
    camera_record_requested = Signal(str)
    camera_fullscreen_requested = Signal(str)
    camera_reconnect_requested = Signal(str)
    camera_settings_requested = Signal(str)
    add_camera_requested = Signal()

    def __init__(
        self,
        layout_manager: LayoutManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("workspace")

        self._layout_manager = layout_manager
        self._camera_widgets: dict[str, CameraWidget] = {}
        self._camera_order: list[str] = []
        self._group_filter_ids: Optional[set[str]] = None

        self._grid_container = QWidget(self)
        self._grid_container.setObjectName("gridContainer")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(0)

        self._empty_label = QLabel("No cameras added.\nClick + to add a camera.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #8892A4; font-size: 14px; font-weight: 500;"
        )

        self._stack = QStackedLayout(self)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self._stack.addWidget(self._grid_container)
        self._stack.addWidget(self._empty_label)
        self._stack.setCurrentIndex(1)

        self._empty_cells: list[EmptyCameraCell] = []
        self._active_empty_cells: set[int] = set()
        self._layout_manager.layout_changed.connect(self._rebuild_grid)

    # ── Camera lifecycle ──────────────────────────────────

    def add_camera(self, info: CameraInfo) -> CameraWidget:
        if info.id in self._camera_widgets:
            return self._camera_widgets[info.id]

        widget = CameraWidget(info)
        widget.snapshot_requested.connect(self.camera_snapshot_requested.emit)
        widget.record_requested.connect(self.camera_record_requested.emit)
        widget.fullscreen_requested.connect(self._on_camera_fullscreen)
        widget.reconnect_requested.connect(self.camera_reconnect_requested.emit)
        widget.settings_requested.connect(self.camera_settings_requested.emit)

        self._camera_widgets[info.id] = widget
        self._camera_order.append(info.id)
        self._sync_camera_ids_to_layout()
        self._rebuild_grid()
        return widget

    def remove_camera(self, camera_id: str) -> None:
        widget = self._camera_widgets.pop(camera_id, None)
        self._camera_order = [cid for cid in self._camera_order if cid != camera_id]
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()

        self._sync_camera_ids_to_layout()
        self._rebuild_grid()

    def get_widget(self, camera_id: str) -> Optional[CameraWidget]:
        return self._camera_widgets.get(camera_id)

    # ── Group filtering ───────────────────────────────────

    def set_group_filter(self, visible_ids: Optional[set[str]]) -> None:
        """Filter workspace to show only cameras in visible_ids.

        Args:
            visible_ids: Set of camera IDs to display, or None to show all.
        """
        self._group_filter_ids = visible_ids
        self._sync_camera_ids_to_layout()
        self._rebuild_grid()

    def clear_group_filter(self) -> None:
        """Clear the group filter and show all cameras."""
        self._group_filter_ids = None
        self._sync_camera_ids_to_layout()
        self._rebuild_grid()

    def _sync_camera_ids_to_layout(self) -> None:
        """Push filtered camera IDs to LayoutManager."""
        filtered = self._get_visible_ids()
        self._layout_manager.set_camera_ids(filtered)

    def _get_visible_ids(self) -> list[str]:
        """Return camera IDs currently visible (filtered or all)."""
        if self._group_filter_ids is None:
            return self._camera_order
        return [cid for cid in self._camera_order if cid in self._group_filter_ids]

    # ── Frame / status routing ────────────────────────────

    def feed_frame(self, frame: FrameData) -> None:
        widget = self._camera_widgets.get(frame.camera_id)
        if widget is not None:
            widget.update_frame(frame)

    def set_camera_status(self, camera_id: str, status: CameraStatus) -> None:
        widget = self._camera_widgets.get(camera_id)
        if widget is not None:
            widget.set_status(status)

    # ── Fullscreen ────────────────────────────────────────

    def _on_camera_fullscreen(self, camera_id: str) -> None:
        if self._layout_manager.is_fullscreen:
            self._layout_manager.exit_fullscreen()
        else:
            self._layout_manager.enter_fullscreen(camera_id)
        self.camera_fullscreen_requested.emit(camera_id)

    def exit_fullscreen(self) -> None:
        self._layout_manager.exit_fullscreen()

    # ── Grid rebuild (core logic) ─────────────────────────

    def _rebuild_grid(self, _grid_name: str = "") -> None:
        visible = self._get_visible_ids()
        if not visible:
            self._show_empty(True)
            return

        self._show_empty(False)

        assignments = self._layout_manager.assignments()
        raw = self._layout_manager.cell_size()
        cell_size = QSize(int(raw.width() * 0.66), int(raw.height() * 0.66))
        cell_size = QSize(int(raw.width() * 1), int(raw.height() * 1))

        self._clear_grid_layout()

        for asgn in assignments:
            cell = asgn.cell
            if asgn.camera_id is not None:
                widget = self._camera_widgets.get(asgn.camera_id)
                if widget is not None:
                    widget.setFixedSize(cell_size)
                    self._grid_layout.addWidget(widget, cell.row, cell.col)
            else:
                empty = self._get_or_create_empty_cell()
                empty.setFixedSize(cell_size)
                self._grid_layout.addWidget(empty, cell.row, cell.col)

        self._grid_container.updateGeometry()

    def _clear_grid_layout(self) -> None:
        """Remove all widgets from grid layout without destroying them."""
        self._active_empty_cells.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _get_or_create_empty_cell(self) -> EmptyCameraCell:
        for i, cell in enumerate(self._empty_cells):
            if i not in self._active_empty_cells:
                self._active_empty_cells.add(i)
                return cell
        cell = EmptyCameraCell()
        cell.add_requested.connect(self.add_camera_requested.emit)
        idx = len(self._empty_cells)
        self._empty_cells.append(cell)
        self._active_empty_cells.add(idx)
        return cell

    def _show_empty(self, show: bool) -> None:
        self._stack.setCurrentIndex(1 if show else 0)
