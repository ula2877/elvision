"""
Stream resilience — reconnect policy with exponential backoff,
bandwidth monitoring, and latency tracking.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import LogService
from app.models import CameraStatus, ConnectionStats


@dataclass
class ReconnectPolicy:
    """Exponential backoff reconnect policy.

    Attributes:
        initial_interval: First retry delay in seconds.
        max_interval: Upper bound for the delay.
        multiplier: Factor by which the delay grows each attempt.
        max_attempts: 0 means infinite retries.
        jitter: Random jitter ratio (0.0–1.0) to prevent thundering herd.
    """

    initial_interval: float = 1.0
    max_interval: float = 60.0
    multiplier: float = 2.0
    max_attempts: int = 0  # 0 = infinite
    jitter: float = 0.25

    _attempt: int = field(default=0, init=False, repr=False)
    _current_interval: float = field(default=0.0, init=False, repr=False)

    def reset(self) -> None:
        self._attempt = 0
        self._current_interval = 0.0

    @property
    def attempt(self) -> int:
        return self._attempt

    def next_delay(self) -> float:
        """Calculate the delay before the next retry attempt."""
        import random

        if self._attempt == 0:
            self._current_interval = self.initial_interval
        else:
            self._current_interval = min(
                self._current_interval * self.multiplier,
                self.max_interval,
            )
        self._attempt += 1

        if self.jitter > 0:
            jitter_range = self._current_interval * self.jitter
            return self._current_interval + random.uniform(-jitter_range, jitter_range)

        return self._current_interval

    def should_retry(self) -> bool:
        """Return True if we should attempt another reconnect."""
        if self.max_attempts == 0:
            return True
        return self._attempt < self.max_attempts


class StreamMonitor:
    """Per-stream health monitor with bandwidth and latency tracking."""

    def __init__(self, camera_id: str) -> None:
        self._camera_id = camera_id
        self._stats = ConnectionStats(camera_id=camera_id)
        self._log = LogService.instance()

        self._frame_timestamps: list[float] = []
        self._byte_timestamps: list[float] = []
        self._bytes_received: int = 0
        self._window_size: int = 60  # track last 60 frames

    def record_frame(self, frame_size_bytes: int = 0) -> None:
        now = time.time()
        self._frame_timestamps.append(now)
        self._byte_timestamps.append(now)
        self._bytes_received += frame_size_bytes

        if len(self._frame_timestamps) > self._window_size:
            self._frame_timestamps = self._frame_timestamps[-self._window_size:]
        if len(self._byte_timestamps) > self._window_size:
            self._byte_timestamps = self._byte_timestamps[-self._window_size:]

    def compute_fps(self) -> float:
        """Compute current FPS from recent frame timestamps."""
        if len(self._frame_timestamps) < 2:
            return 0.0

        window = min(self._window_size, len(self._frame_timestamps))
        recent = self._frame_timestamps[-window:]
        elapsed = recent[-1] - recent[0]
        if elapsed <= 0:
            return 0.0

        return (len(recent) - 1) / elapsed

    def compute_bandwidth_kbps(self) -> float:
        """Compute current bandwidth from recent byte timestamps."""
        if len(self._byte_timestamps) < 2:
            return 0.0

        window = min(self._window_size, len(self._byte_timestamps))
        recent_times = self._byte_timestamps[-window:]
        elapsed = recent_times[-1] - recent_times[0]
        if elapsed <= 0:
            return 0.0

        bits = self._bytes_received * 8
        return (bits / elapsed) / 1000.0

    def record_reconnect(self) -> None:
        self._stats.reconnect_attempts += 1

    def record_error(self, message: str) -> None:
        self._stats.last_error = message
        self._stats.status = CameraStatus.ERROR

    def set_status(self, status: CameraStatus) -> None:
        self._stats.status = status

    def get_stats(self) -> ConnectionStats:
        self._stats.fps_current = self.compute_fps()
        self._stats.bandwidth_kbps = self.compute_bandwidth_kbps()
        if self._frame_timestamps:
            self._stats.uptime_seconds = time.time() - self._frame_timestamps[0]
        return self._stats

    def reset(self) -> None:
        self._stats = ConnectionStats(camera_id=self._camera_id)
        self._frame_timestamps.clear()
        self._byte_timestamps.clear()
        self._bytes_received = 0
