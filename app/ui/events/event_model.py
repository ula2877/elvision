from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QPixmap, QColor

from app.core.events.models import EventRecord, EVENT_TYPE_COLORS


_COLUMNS = ["snapshot", "time", "camera", "group", "event", "confidence", "status", "notes"]
_COL_LABELS = ["Snapshot", "Date & Time", "Camera", "Group", "Event", "Confidence", "Status", "Notes"]

COL_SNAPSHOT = 0
COL_TIME = 1
COL_CAMERA = 2
COL_GROUP = 3
COL_EVENT = 4
COL_CONFIDENCE = 5
COL_STATUS = 6
COL_NOTES = 7

_THUMB_SIZE = 48


class EventTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._events: list[EventRecord] = []
        self._thumbnails: dict[int, QPixmap] = {}

    def set_events(self, events: list[EventRecord]) -> None:
        self.beginResetModel()
        self._events = events
        self._thumbnails.clear()
        self.endResetModel()

    def event_at(self, index: int) -> Optional[EventRecord]:
        if 0 <= index < len(self._events):
            return self._events[index]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._events)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COL_LABELS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._events):
            return None
        ev = self._events[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.UserRole:
            return ev.id

        if col == COL_SNAPSHOT:
            if role in (Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.DisplayRole):
                return self._get_thumbnail(ev)
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_TIME:
                lt = time.localtime(ev.timestamp)
                return f"{time.strftime('%d %b %Y', lt)}\n{time.strftime('%H:%M:%S', lt)}"
            if col == COL_CAMERA:
                return ev.camera_name or ev.camera_id
            if col == COL_GROUP:
                return ev.group_name or "-"
            if col == COL_EVENT:
                return ev.event_label
            if col == COL_CONFIDENCE:
                return f"{ev.confidence:.1%}" if ev.confidence > 0 else "-"
            if col == COL_STATUS:
                return ev.status.capitalize()
            if col == COL_NOTES:
                return ev.notes if ev.notes else "-"

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_SNAPSHOT and ev.snapshot_path:
                return ev.snapshot_path
            if col == COL_TIME:
                lt = time.localtime(ev.timestamp)
                return time.strftime("%Y-%m-%d  %H:%M:%S", lt)
            if col == COL_NOTES:
                return ev.notes or "-"
            return self.data(index, Qt.ItemDataRole.DisplayRole)

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == COL_EVENT:
                color = EVENT_TYPE_COLORS.get(ev.event_type, "#6B7280")
                return QColor(color)
            if col == COL_STATUS:
                return QColor("#10B981" if ev.status == "new" else "#64748B")

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (COL_CONFIDENCE,):
                return Qt.AlignmentFlag.AlignCenter
            if col == COL_SNAPSHOT:
                return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.SizeHintRole and col == COL_SNAPSHOT:
            return Qt.QSize(_THUMB_SIZE, _THUMB_SIZE)

        # Sort role
        if role == Qt.ItemDataRole.UserRole + 1:
            if col == COL_TIME:
                return ev.timestamp
            if col == COL_CAMERA:
                return ev.camera_name or ev.camera_id
            if col == COL_GROUP:
                return ev.group_name or ""
            if col == COL_EVENT:
                return ev.event_type
            if col == COL_CONFIDENCE:
                return ev.confidence
            if col == COL_STATUS:
                return ev.status
            if col == COL_NOTES:
                return ev.notes

        return None

    def _get_thumbnail(self, ev: EventRecord) -> Optional[QPixmap]:
        if ev.id in self._thumbnails:
            return self._thumbnails[ev.id]
        if not ev.snapshot_path:
            return None
        path = Path(ev.snapshot_path)
        if path.exists():
            pix = QPixmap(str(path))
            thumb = pix.scaled(_THUMB_SIZE, _THUMB_SIZE,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._thumbnails[ev.id] = thumb
            return thumb
        return None


class EventSortProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole + 1)
        self.setDynamicSortFilter(True)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        col = left.column()
        src = self.sourceModel()
        if col in (COL_TIME, COL_CONFIDENCE):
            lv = src.data(left, Qt.ItemDataRole.UserRole + 1)
            rv = src.data(right, Qt.ItemDataRole.UserRole + 1)
            if lv is not None and rv is not None:
                return float(lv) < float(rv)
        return super().lessThan(left, right)
