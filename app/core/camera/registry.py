"""
CameraRegistry — single source of truth for all camera resources.

Every camera entry stores:
    camera_id, CameraInfo, VideoSource, CameraWorker, QThread,
    CameraWidget, CameraState, retry_count, last_frame_time, statistics.

Only CameraManager may mutate this registry.
CameraWidget only observes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QThread

from app.core.camera.base import VideoSource
from app.core.camera.resilience import ReconnectPolicy, StreamMonitor
from app.models import CameraInfo, CameraState, CameraStatus, ConnectionStats, camera_state_to_status


@dataclass
class CameraEntry:
    """Complete record of a camera and all its owned resources."""

    info: CameraInfo
    source: VideoSource
    worker: object = None  # CameraWorker — forward ref to avoid circular import
    thread: Optional[QThread] = None
    widget: object = None  # CameraWidget — forward ref
    state: CameraState = CameraState.IDLE
    reconnect_policy: Optional[ReconnectPolicy] = None
    stream_monitor: Optional[StreamMonitor] = None
    retry_count: int = 0
    last_frame_time: float = 0.0
    first_frame_received: bool = False
    start_time: float = field(default_factory=time.time)

    @property
    def camera_id(self) -> str:
        return self.info.id

    @property
    def has_worker(self) -> bool:
        return self.worker is not None

    @property
    def has_thread(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def get_stats(self) -> ConnectionStats:
        if self.stream_monitor is not None:
            return self.stream_monitor.get_stats()
        return ConnectionStats(camera_id=self.camera_id)


class CameraRegistry:
    """Thread-safe registry of all camera entries.

    This is the single source of truth. All camera state, resources,
    and metadata live here. CameraManager mutates; everyone else reads.
    """

    def __init__(self) -> None:
        self._entries: dict[str, CameraEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, camera_id: str) -> bool:
        return camera_id in self._entries

    def __iter__(self):
        return iter(self._entries.values())

    def add(self, entry: CameraEntry) -> None:
        self._entries[entry.camera_id] = entry

    def remove(self, camera_id: str) -> Optional[CameraEntry]:
        return self._entries.pop(camera_id, None)

    def get(self, camera_id: str) -> Optional[CameraEntry]:
        return self._entries.get(camera_id)

    def get_source(self, camera_id: str) -> Optional[VideoSource]:
        entry = self._entries.get(camera_id)
        return entry.source if entry else None

    def get_worker(self, camera_id: str) -> object:
        entry = self._entries.get(camera_id)
        return entry.worker if entry else None

    def get_thread(self, camera_id: str) -> Optional[QThread]:
        entry = self._entries.get(camera_id)
        return entry.thread if entry else None

    def get_widget(self, camera_id: str) -> object:
        entry = self._entries.get(camera_id)
        return entry.widget if entry else None

    def get_state(self, camera_id: str) -> CameraState:
        entry = self._entries.get(camera_id)
        return entry.state if entry else CameraState.IDLE

    def set_state(self, camera_id: str, state: CameraState) -> None:
        entry = self._entries.get(camera_id)
        if entry:
            entry.state = state

    def set_worker(self, camera_id: str, worker: object) -> None:
        entry = self._entries.get(camera_id)
        if entry:
            entry.worker = worker

    def set_thread(self, camera_id: str, thread: Optional[QThread]) -> None:
        entry = self._entries.get(camera_id)
        if entry:
            entry.thread = thread

    def set_widget(self, camera_id: str, widget: object) -> None:
        entry = self._entries.get(camera_id)
        if entry:
            entry.widget = widget

    def has_active_worker(self, camera_id: str) -> bool:
        entry = self._entries.get(camera_id)
        if entry is None:
            return False
        return entry.has_worker

    def active_camera_ids(self) -> list[str]:
        return [eid for eid, e in self._entries.items() if e.has_worker]

    def all_camera_ids(self) -> list[str]:
        return list(self._entries.keys())

    def all_entries(self) -> list[CameraEntry]:
        return list(self._entries.values())

    def count(self) -> int:
        return len(self._entries)

    # ── Centralized status counters ─────────────────────────────────────────

    def _count_by_status(self, target: CameraStatus) -> int:
        """Count entries whose CameraState maps to the given CameraStatus."""
        return sum(
            1
            for e in self._entries.values()
            if camera_state_to_status(e.state) == target
        )

    def total_count(self) -> int:
        """Total number of registered cameras."""
        return len(self._entries)

    def online_count(self) -> int:
        """Cameras in ONLINE state (STREAMING → CameraStatus.ONLINE)."""
        return self._count_by_status(CameraStatus.ONLINE)

    def offline_count(self) -> int:
        """Cameras in OFFLINE state (IDLE, STOPPING, STOPPED)."""
        return self._count_by_status(CameraStatus.OFFLINE)

    def connecting_count(self) -> int:
        """Cameras in CONNECTING state (CONNECTING, CONNECTED)."""
        return self._count_by_status(CameraStatus.CONNECTING)

    def error_count(self) -> int:
        """Cameras in ERROR state."""
        return self._count_by_status(CameraStatus.ERROR)

    def buffering_count(self) -> int:
        """Cameras in BUFFERING state (BUFFERING, RECONNECTING)."""
        return self._count_by_status(CameraStatus.BUFFERING)

    def status_summary(self) -> dict[str, int]:
        """Return a complete status count snapshot."""
        return {
            "total": self.total_count(),
            "online": self.online_count(),
            "offline": self.offline_count(),
            "connecting": self.connecting_count(),
            "error": self.error_count(),
            "buffering": self.buffering_count(),
        }

    def clear(self) -> None:
        self._entries.clear()
