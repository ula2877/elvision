from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from app.core.events.models import EventRecord, EventFilter, EVENT_STATUS_NEW


_DB_PATH = Path("data/events.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL NOT NULL,
    camera_id       TEXT NOT NULL,
    camera_name     TEXT NOT NULL DEFAULT '',
    group_name      TEXT NOT NULL DEFAULT '',
    event_type      TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    snapshot_path   TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new',
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_camera_id ON events(camera_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
"""


class EventDatabase:
    def __init__(self, db_path: str | Path = _DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def insert(self, record: EventRecord) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO events
                   (timestamp, camera_id, camera_name, group_name, event_type,
                    confidence, snapshot_path, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp,
                    record.camera_id,
                    record.camera_name,
                    record.group_name,
                    record.event_type,
                    record.confidence,
                    record.snapshot_path,
                    record.status or EVENT_STATUS_NEW,
                    record.notes,
                ),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def update_status(self, event_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE events SET status=? WHERE id=?", (status, event_id)
            )
            self._conn.commit()

    def update_notes(self, event_id: int, notes: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE events SET notes=? WHERE id=?", (notes, event_id)
            )
            self._conn.commit()

    def delete(self, event_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE id=?", (event_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_many(self, event_ids: list[int]) -> int:
        if not event_ids:
            return 0
        placeholders = ",".join("?" for _ in event_ids)
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM events WHERE id IN ({placeholders})", event_ids
            )
            self._conn.commit()
            return cur.rowcount

    def delete_all(self) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM events")
            self._conn.commit()
            return cur.rowcount

    def delete_by_filter(self, filter_: Optional[EventFilter] = None) -> int:
        sql = "DELETE FROM events WHERE 1=1"
        params: list = []

        if filter_:
            if filter_.search:
                sql += " AND (camera_name LIKE ? OR notes LIKE ? OR event_type LIKE ?)"
                like = f"%{filter_.search}%"
                params.extend([like, like, like])
            if filter_.date_from:
                ts_from = _parse_date(filter_.date_from)
                if ts_from is not None:
                    sql += " AND timestamp >= ?"
                    params.append(ts_from)
            if filter_.date_to:
                ts_to = _parse_date(filter_.date_to, end_of_day=True)
                if ts_to is not None:
                    sql += " AND timestamp <= ?"
                    params.append(ts_to)
            if filter_.camera_id:
                sql += " AND camera_id=?"
                params.append(filter_.camera_id)
            if filter_.group_name:
                sql += " AND group_name=?"
                params.append(filter_.group_name)
            if filter_.event_type:
                sql += " AND event_type=?"
                params.append(filter_.event_type)
            if filter_.status:
                sql += " AND status=?"
                params.append(filter_.status)

        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def delete_by_status(self, status: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE status=?", (status,)
            )
            self._conn.commit()
            return cur.rowcount

    def get_by_id(self, event_id: int) -> Optional[EventRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM events WHERE id=?", (event_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def query(self, filter_: Optional[EventFilter] = None,
              limit: int = 500, offset: int = 0) -> list[EventRecord]:
        sql = "SELECT * FROM events WHERE 1=1"
        params: list = []

        if filter_:
            if filter_.search:
                sql += " AND (camera_name LIKE ? OR notes LIKE ? OR event_type LIKE ?)"
                like = f"%{filter_.search}%"
                params.extend([like, like, like])
            if filter_.date_from:
                ts_from = _parse_date(filter_.date_from)
                if ts_from is not None:
                    sql += " AND timestamp >= ?"
                    params.append(ts_from)
            if filter_.date_to:
                ts_to = _parse_date(filter_.date_to, end_of_day=True)
                if ts_to is not None:
                    sql += " AND timestamp <= ?"
                    params.append(ts_to)
            if filter_.camera_id:
                sql += " AND camera_id=?"
                params.append(filter_.camera_id)
            if filter_.group_name:
                sql += " AND group_name=?"
                params.append(filter_.group_name)
            if filter_.event_type:
                sql += " AND event_type=?"
                params.append(filter_.event_type)
            if filter_.status:
                sql += " AND status=?"
                params.append(filter_.status)

        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_record(r) for r in rows]

    def count(self, filter_: Optional[EventFilter] = None) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE 1=1"
        params: list = []

        if filter_:
            if filter_.search:
                sql += " AND (camera_name LIKE ? OR notes LIKE ? OR event_type LIKE ?)"
                like = f"%{filter_.search}%"
                params.extend([like, like, like])
            if filter_.date_from:
                ts_from = _parse_date(filter_.date_from)
                if ts_from is not None:
                    sql += " AND timestamp >= ?"
                    params.append(ts_from)
            if filter_.date_to:
                ts_to = _parse_date(filter_.date_to, end_of_day=True)
                if ts_to is not None:
                    sql += " AND timestamp <= ?"
                    params.append(ts_to)
            if filter_.camera_id:
                sql += " AND camera_id=?"
                params.append(filter_.camera_id)
            if filter_.group_name:
                sql += " AND group_name=?"
                params.append(filter_.group_name)
            if filter_.event_type:
                sql += " AND event_type=?"
                params.append(filter_.event_type)
            if filter_.status:
                sql += " AND status=?"
                params.append(filter_.status)

        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            return row[0] if row else 0

    def distinct_cameras(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT camera_id FROM events ORDER BY camera_id"
            ).fetchall()
            return [r[0] for r in rows]

    def distinct_groups(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT group_name FROM events WHERE group_name != '' ORDER BY group_name"
            ).fetchall()
            return [r[0] for r in rows]

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    @staticmethod
    def _row_to_record(row: tuple) -> EventRecord:
        return EventRecord(
            id=row[0],
            timestamp=row[1],
            camera_id=row[2],
            camera_name=row[3],
            group_name=row[4],
            event_type=row[5],
            confidence=row[6],
            snapshot_path=row[7],
            status=row[8],
            notes=row[9],
        )


def _parse_date(date_str: str, end_of_day: bool = False) -> Optional[float]:
    import datetime
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt.timestamp()
        except ValueError:
            continue
    return None
