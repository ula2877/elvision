"""
VideoSource — abstract interface for all video input adapters.
Every source type (Webcam, RTSP, YouTube, etc.) implements this contract.
The rest of the application communicates only through this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models import CameraInfo, CameraStatus, FrameData, SourceMetadata


class VideoSource(ABC):
    """Abstract base class for all video sources.

    Lifecycle: __init__ → open() → read() → close()
    Thread safety: Each instance is accessed from a single worker thread.
    """

    def __init__(self, camera_info: CameraInfo) -> None:
        self._info = camera_info
        self._status = CameraStatus.OFFLINE
        self._metadata = SourceMetadata()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    @abstractmethod
    def open(self) -> bool:
        """Open the source connection. Returns True on success."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release all resources. Must be safe to call multiple times."""
        ...

    @abstractmethod
    def read(self) -> Optional[FrameData]:
        """Read and return the next frame, or None if unavailable."""
        ...

    @abstractmethod
    def reconnect(self) -> bool:
        """Tear down and re-establish the connection. Returns True on success."""
        ...

    # ── State ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def is_opened(self) -> bool:
        """Return True if the source is currently connected and ready to read."""
        ...

    @property
    def info(self) -> CameraInfo:
        return self._info

    @property
    def status(self) -> CameraStatus:
        return self._status

    def get_metadata(self) -> SourceMetadata:
        """Return runtime metadata about the opened stream."""
        return self._metadata
