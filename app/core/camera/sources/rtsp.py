"""
RTSPSource — RTSP/IP camera adapter via OpenCV.
Supports: TCP/UDP transport, authentication, buffer config, reconnect.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Optional
from urllib.parse import urlparse, urlunparse, quote

import cv2

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import (
    CameraInfo,
    CameraStatus,
    FrameData,
    SourceMetadata,
    TransportProtocol,
)
from app.utils.security import mask_url


class RTSPSource(VideoSource):
    """RTSP / IP camera source via OpenCV VideoCapture."""

    def __init__(self, camera_info: CameraInfo) -> None:
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = Lock()
        self._log = LogService.instance()
        self._frame_count = 0
        self._connection_timeout = camera_info.source_config.connection_timeout_sec
        self._protocol = camera_info.source_config.transport_protocol

    def open(self) -> bool:
        with self._lock:
            try:
                url = self._build_url()
                self._log.camera_event(
                    self._info.id,
                    "Connecting to RTSP: %s" % mask_url(url),
                )

                cap_backend = self._get_backend()
                if cap_backend is not None:
                    self._cap = cv2.VideoCapture(url, cap_backend)
                else:
                    self._cap = cv2.VideoCapture(url)

                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self._info.source_config.buffer_size)

                if self._protocol == TransportProtocol.TCP:
                    try:
                        self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                                       int(self._connection_timeout * 1000))
                    except Exception:
                        pass

                if not self._cap.isOpened():
                    self._status = CameraStatus.ERROR
                    self._log.camera_event(
                        self._info.id,
                        "Failed to connect: %s" % mask_url(url),
                    )
                    return False

                self._metadata.native_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._metadata.native_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._metadata.native_fps = self._cap.get(cv2.CAP_PROP_FPS)
                self._metadata.is_network_stream = True

                self._status = CameraStatus.ONLINE
                self._log.camera_event(
                    self._info.id,
                    "RTSP connected: %dx%d @ %.0f fps" % (
                        self._metadata.native_width,
                        self._metadata.native_height,
                        self._metadata.native_fps,
                    ),
                )
                return True

            except Exception as exc:
                self._status = CameraStatus.ERROR
                self._log.error("RTSP %s open error: %s", self._info.id, exc)
                return False

    def close(self) -> None:
        with self._lock:
            try:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                self._status = CameraStatus.OFFLINE
            except Exception as exc:
                self._log.error("RTSP %s close error: %s", self._info.id, exc)

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
            self._log.error("RTSP %s read error: %s", self._info.id, exc)
            self._status = CameraStatus.ERROR
            return None

    def reconnect(self) -> bool:
        self.close()
        return self.open()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def _build_url(self) -> str:
        """Construct the RTSP URL with embedded credentials if provided."""
        parsed = urlparse(self._info.uri)

        if self._info.username and self._info.password:
            encoded_user = quote(self._info.username, safe="")
            encoded_pass = quote(self._info.password, safe="")
            auth = f"{encoded_user}:{encoded_pass}@"
            return urlunparse(parsed._replace(netloc=auth + parsed.netloc))

        return self._info.uri

    def _get_backend(self) -> Optional[int]:
        """Select OpenCV backend based on transport protocol."""
        if self._protocol == TransportProtocol.TCP:
            try:
                return cv2.CAP_FFMPEG
            except AttributeError:
                return None
        return None
