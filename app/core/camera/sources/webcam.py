"""
WebcamSource — local USB camera adapter via OpenCV.
Supports multiple cameras by device index, resolution, and FPS selection.
"""
from __future__ import annotations

import time
from typing import Optional

import cv2

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import CameraInfo, CameraStatus, FrameData, SourceMetadata


class WebcamSource(VideoSource):
    """Local webcam / USB camera source via OpenCV VideoCapture."""

    _available_cache: Optional[list[int]] = None

    def __init__(self, camera_info: CameraInfo) -> None:
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._log = LogService.instance()
        self._frame_count = 0
        self._start_time = 0.0

    @staticmethod
    def enumerate_devices(max_probe: int = 10) -> list[int]:
        """Probe available webcam indices by attempting to open each one.

        Returns a list of working device indices. Results are cached.
        """
        if WebcamSource._available_cache is not None:
            return WebcamSource._available_cache

        available: list[int] = []
        for idx in range(max_probe):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                available.append(idx)
                cap.release()
            else:
                cap.release()

        WebcamSource._available_cache = available
        return available

    @staticmethod
    def is_device_available(device_index: int) -> bool:
        """Check if a specific webcam index is available."""
        available = WebcamSource.enumerate_devices(max_probe=device_index + 1)
        return device_index in available

    @staticmethod
    def invalidate_cache() -> None:
        """Clear the device availability cache. Call when hardware changes."""
        WebcamSource._available_cache = None

    def open(self) -> bool:
        try:
            device_index = int(self._info.uri)
        except (ValueError, TypeError):
            self._status = CameraStatus.ERROR
            self._log.error(
                "Invalid webcam index '%s' for %s", self._info.uri, self._info.id,
            )
            return False

        if not self.is_device_available(device_index):
            self._status = CameraStatus.ERROR
            self._log.error(
                "Webcam index %d not available for %s (devices: %s)",
                device_index,
                self._info.id,
                self.enumerate_devices(),
            )
            return False

        try:
            self._cap = cv2.VideoCapture(device_index)

            if not self._cap.isOpened():
                self._status = CameraStatus.ERROR
                self._log.camera_event(
                    self._info.id, "Failed to open webcam %d" % device_index,
                )
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._info.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._info.height)
            self._cap.set(cv2.CAP_PROP_FPS, self._info.fps)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self._info.source_config.buffer_size)

            self._metadata.native_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._metadata.native_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._metadata.native_fps = self._cap.get(cv2.CAP_PROP_FPS)

            self._status = CameraStatus.ONLINE
            self._start_time = time.time()
            self._log.camera_event(
                self._info.id,
                "Webcam opened: %dx%d @ %d fps" % (
                    self._metadata.native_width,
                    self._metadata.native_height,
                    int(self._metadata.native_fps),
                ),
            )
            return True

        except Exception as exc:
            self._status = CameraStatus.ERROR
            self._log.error("Webcam %s open error: %s", self._info.id, exc)
            return False

    def close(self) -> None:
        try:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._status = CameraStatus.OFFLINE
            self._log.camera_event(self._info.id, "Webcam closed")
        except Exception as exc:
            self._log.error("Webcam %s close error: %s", self._info.id, exc)

    def read(self) -> Optional[FrameData]:
        if self._cap is None or not self._cap.isOpened():
            return None

        try:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self._status = CameraStatus.DISCONNECTED
                return None

            self._frame_count += 1
            h, w = frame.shape[:2]

            return FrameData(
                camera_id=self._info.id,
                timestamp=time.time(),
                frame_number=self._frame_count,
                width=w,
                height=h,
                fps=float(self._info.fps),
                data=frame,
            )
        except Exception as exc:
            self._log.error("Webcam %s read error: %s", self._info.id, exc)
            self._status = CameraStatus.ERROR
            return None

    def reconnect(self) -> bool:
        self.close()
        return self.open()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
