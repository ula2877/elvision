"""
LayoutManager — calculates grid positions, pagination, and cell assignments.
Pure logic: no Qt widgets, no signal-slot for layout rebuilds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QRect, QSize, Signal

from app.core.logging import LogService
from app.models import LayoutGrid


@dataclass
class CellPosition:
    """Position and size of a single cell in the layout grid."""

    index: int
    row: int
    col: int
    rect: QRect


@dataclass
class CellAssignment:
    """Maps a cell index to its content (camera_id or None for empty)."""

    cell: CellPosition
    camera_id: Optional[str]


class LayoutManager(QObject):
    """Pure-logic grid calculator.

    Responsibilities:
    - Compute cell positions for the current grid
    - Handle pagination (slice camera list into pages)
    - Track which camera is in fullscreen isolation
    - Emit layout_changed only when grid/pagination actually changes
    """

    layout_changed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._grid: LayoutGrid = LayoutGrid.GRID_1X1
        self._workspace_size: QSize = QSize(1920, 1080)
        self._camera_ids: list[str] = []
        self._page: int = 0
        self._gap: int = 4
        self._fullscreen_id: Optional[str] = None
        self._saved_grid: Optional[LayoutGrid] = None
        self._log = LogService.instance()

    # ── Grid configuration ────────────────────────────────

    def set_grid(self, grid: LayoutGrid) -> None:
        if grid == self._grid:
            return
        self._grid = grid
        self._page = 0
        self._fullscreen_id = None
        self._log.info(
            "Layout changed to %s (%d×%d, capacity=%d)",
            grid.name, grid.rows, grid.cols, grid.capacity,
        )
        self.layout_changed.emit(grid.name)

    def set_workspace_size(self, size: QSize) -> None:
        if size == self._workspace_size:
            return
        self._workspace_size = size

    def set_camera_ids(self, ids: list[str]) -> None:
        self._camera_ids = list(ids)
        self._clamp_page()

    @property
    def gap(self) -> int:
        return self._gap

    @gap.setter
    def gap(self, value: int) -> None:
        self._gap = max(0, value)

    @property
    def current_grid(self) -> LayoutGrid:
        return self._grid

    @property
    def page(self) -> int:
        return self._page

    @property
    def camera_count(self) -> int:
        return len(self._camera_ids)

    # ── Pagination ────────────────────────────────────────

    def next_page(self) -> bool:
        if self._page < self._max_page():
            self._page += 1
            self.layout_changed.emit(self._grid.name)
            return True
        return False

    def previous_page(self) -> bool:
        if self._page > 0:
            self._page -= 1
            self.layout_changed.emit(self._grid.name)
            return True
        return False

    def _max_page(self) -> int:
        cap = self._grid.capacity
        if cap == 0:
            return 0
        return max(0, math.ceil(len(self._camera_ids) / cap) - 1)

    def _clamp_page(self) -> None:
        mx = self._max_page()
        if self._page > mx:
            self._page = mx

    def visible_camera_ids(self) -> list[str]:
        """Camera IDs visible on the current page, in order."""
        cap = self._grid.capacity
        if cap == 0 or not self._camera_ids:
            return []
        start = self._page * cap
        end = min(start + cap, len(self._camera_ids))
        return self._camera_ids[start:end]

    # ── Cell geometry ─────────────────────────────────────

    def cell_size(self) -> QSize:
        """Return the uniform cell dimensions for the current grid.
        All cells share identical width and height.
        """
        rows, cols = self._grid.rows, self._grid.cols
        if rows == 0 or cols == 0:
            return QSize(0, 0)
        tw = self._workspace_size.width()
        th = self._workspace_size.height()
        cw = (tw - self._gap * (cols + 1)) // cols
        ch = (th - self._gap * (rows + 1)) // rows
        return QSize(max(cw, 1), max(ch, 1))

    def cells(self) -> list[CellPosition]:
        """Return exactly rows×cols cell positions, regardless of camera count."""
        rows, cols = self._grid.rows, self._grid.cols
        if rows == 0 or cols == 0:
            return []

        uniform = self.cell_size()
        cw, ch = uniform.width(), uniform.height()

        result: list[CellPosition] = []
        idx = 0
        for r in range(rows):
            for c in range(cols):
                x = self._gap + c * (cw + self._gap)
                y = self._gap + r * (ch + self._gap)
                result.append(CellPosition(idx, r, c, QRect(x, y, cw, ch)))
                idx += 1
        return result

    # ── Cell content mapping ──────────────────────────────

    def assignments(self) -> list[CellAssignment]:
        """Map each cell to a camera_id or None (empty slot).

        When in fullscreen mode, exactly one cell is assigned and the
        rest are None.
        """
        cells = self.cells()
        visible = self.visible_camera_ids()

        if self._fullscreen_id:
            result: list[CellAssignment] = []
            for cell in cells:
                cid = self._fullscreen_id if cell.index == 0 else None
                result.append(CellAssignment(cell, cid))
            return result

        result = []
        for cell in cells:
            cid = visible[cell.index] if cell.index < len(visible) else None
            result.append(CellAssignment(cell, cid))
        return result

    # ── Fullscreen isolation ──────────────────────────────

    def enter_fullscreen(self, camera_id: str) -> None:
        self._saved_grid = self._grid
        self._fullscreen_id = camera_id
        if self._grid != LayoutGrid.GRID_1X1:
            self._grid = LayoutGrid.GRID_1X1
        self.layout_changed.emit(self._grid.name)

    def switch_fullscreen(self, camera_id: str) -> None:
        """Switch to a different camera while keeping fullscreen mode active."""
        if self._fullscreen_id is not None:
            self._fullscreen_id = camera_id
            self.layout_changed.emit(self._grid.name)

    def exit_fullscreen(self) -> None:
        if self._fullscreen_id is not None:
            self._fullscreen_id = None
            if self._saved_grid is not None:
                self._grid = self._saved_grid
                self._saved_grid = None
            self.layout_changed.emit(self._grid.name)

    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen_id is not None

    @property
    def fullscreen_camera_id(self) -> Optional[str]:
        return self._fullscreen_id
