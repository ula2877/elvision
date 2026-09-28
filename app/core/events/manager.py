from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal

from app.core.events.models import (
    EventRecord,
    EVENT_STATUS_NEW,
)
from app.core.events.database import EventDatabase
from app.core.events.snapshot import EventSnapshotter
from app.core.logging import LogService


class EventManager(QObject):
    event_created = Signal(object)  # EventRecord

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._db = EventDatabase()
        self._snapshotter = EventSnapshotter()
        self._log = LogService.instance()
        self._latest_frames: dict[str, np.ndarray] = {}

    def cache_frame(self, camera_id: str, frame: np.ndarray) -> None:
        self._latest_frames[camera_id] = frame

    def add_event(
        self,
        event_type: str,
        camera_id: str,
        camera_name: str = "",
        group_name: str = "",
        confidence: float = 0.0,
        frame: Optional[np.ndarray] = None,
        notes: str = "",
    ) -> Optional[EventRecord]:
        try:
            ts = time.time()
            snapshot_path = ""

            frame_to_use = frame if frame is not None else self._latest_frames.get(camera_id)
            if frame_to_use is not None:
                sp = self._snapshotter.save(frame_to_use, event_type, camera_id, ts)
                if sp is not None:
                    snapshot_path = str(sp.as_posix())

            record = EventRecord(
                timestamp=ts,
                camera_id=camera_id,
                camera_name=camera_name,
                group_name=group_name,
                event_type=event_type,
                confidence=confidence,
                snapshot_path=snapshot_path,
                status=EVENT_STATUS_NEW,
                notes=notes,
            )

            record.id = self._db.insert(record)
            self.event_created.emit(record)
            self._log.info("Event recorded: %s | %s | %s",
                           event_type, camera_id, camera_name)
            return record
        except Exception as exc:
            self._log.error("Failed to record event: %s", exc)
            return None

    def query(self, filter_=None, limit: int = 500, offset: int = 0) -> list[EventRecord]:
        return self._db.query(filter_, limit=limit, offset=offset)

    def count(self, filter_=None) -> int:
        return self._db.count(filter_)

    def delete_event(self, event_id: int) -> bool:
        result = self._db.delete(event_id)
        if result:
            self._log.info("Deleted event id=%d", event_id)
        return result

    def delete_events(self, event_ids: list[int]) -> int:
        result = self._db.delete_many(event_ids)
        if result:
            self._log.info("Deleted %d event(s)", result)
        return result

    def delete_all(self) -> int:
        result = self._db.delete_all()
        if result:
            self._log.info("Deleted all %d event(s)", result)
        return result

    def delete_by_filter(self, filter_=None) -> int:
        result = self._db.delete_by_filter(filter_)
        if result:
            self._log.info("Deleted %d event(s) by filter", result)
        return result

    def delete_by_status(self, status: str) -> int:
        result = self._db.delete_by_status(status)
        if result:
            self._log.info("Deleted %d event(s) with status=%s", result, status)
        return result

    def update_status(self, event_id: int, status: str) -> None:
        self._db.update_status(event_id, status)

    def update_notes(self, event_id: int, notes: str) -> None:
        self._db.update_notes(event_id, notes)

    def get_by_id(self, event_id: int) -> Optional[EventRecord]:
        return self._db.get_by_id(event_id)

    def distinct_cameras(self) -> list[str]:
        return self._db.distinct_cameras()

    def distinct_groups(self) -> list[str]:
        return self._db.distinct_groups()

    def shutdown(self) -> None:
        self._db.close()
