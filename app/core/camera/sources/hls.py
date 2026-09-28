"""
HLSStreamSource — HTTP Live Streaming adapter via OpenCV.
Handles playlist refresh and automatic reconnect for unstable streams.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Optional

import cv2

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import CameraInfo, CameraStatus, FrameData, SourceMetadata


class HLSStreamSource(VideoSource):
    """HLS (.m3u8) live stream source via OpenCV VideoCapture."""

    def __init__(self, camera_info: CameraInfo) -> None:
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = Lock()
        self._log = LogService.instance()
        self._frame_count = 0
        self._consecutive_failures = 0

    def open(self) -> bool:
        with self._lock:
            try:
                url = self._info.uri
                self._log.camera_event(self._info.id, "Connecting to HLS: %s" % url)

                self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self._info.source_config.buffer_size)

                if not self._cap.isOpened():
                    self._status = CameraStatus.ERROR
                    self._log.camera_event(self._info.id, "Failed to open HLS stream")
                    return False

                self._metadata.native_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._metadata.native_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._metadata.native_fps = self._cap.get(cv2.CAP_PROP_FPS)
                self._metadata.is_network_stream = True

                self._status = CameraStatus.ONLINE
                self._consecutive_failures = 0
                self._log.camera_event(
                    self._info.id,
                    "HLS connected: %dx%d" % (
                        self._metadata.native_width,
                        self._metadata.native_height,
                    ),
                )
                return True

            except Exception as exc:
                self._status = CameraStatus.ERROR
                self._log.error("HLS %s open error: %s", self._info.id, exc)
                return False

    def close(self) -> None:
        with self._lock:
            try:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                self._status = CameraStatus.OFFLINE
            except Exception as exc:
                self._log.error("HLS %s close error: %s", self._info.id, exc)

    def read(self) -> Optional[FrameData]:
        if self._cap is None or not self._cap.isOpened():
            return None

        try:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 5:
                    self._status = CameraStatus.DISCONNECTED
                return None

            self._frame_count += 1
            self._consecutive_failures = 0
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
            self._log.error("HLS %s read error: %s", self._info.id, exc)
            self._status = CameraStatus.ERROR
            return None

    def reconnect(self) -> bool:
        self.close()
        return self.open()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
