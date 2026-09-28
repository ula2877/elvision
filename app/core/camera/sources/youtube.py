"""
YoutubeSource — YouTube Live / VOD adapter using yt-dlp + OpenCV.
Resolves the direct stream URL automatically.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import cv2

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import CameraInfo, CameraStatus, FrameData, SourceMetadata


class YoutubeSource(VideoSource):
    """YouTube video / live stream source.

    Uses yt-dlp to resolve the direct stream URL,
    then opens it with OpenCV VideoCapture (FFmpeg backend).
    """

    _QUALITY_MAP = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "worst": "worst[ext=mp4]/worst",
    }

    def __init__(self, camera_info: CameraInfo) -> None:
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = Lock()
        self._log = LogService.instance()
        self._frame_count = 0
        self._resolved_url: str = ""

    def open(self) -> bool:
        with self._lock:
            try:
                if not self._check_ytdlp():
                    self._status = CameraStatus.ERROR
                    self._log.error("yt-dlp is not installed or not in PATH")
                    return False

                self._log.camera_event(self._info.id, "Resolving YouTube URL...")

                stream_url = self._resolve_stream_url()
                if not stream_url:
                    self._status = CameraStatus.ERROR
                    self._log.error("Failed to resolve YouTube stream URL")
                    return False

                self._resolved_url = stream_url
                self._log.camera_event(self._info.id, "Stream URL resolved, connecting...")

                self._cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self._info.source_config.buffer_size)

                if not self._cap.isOpened():
                    self._status = CameraStatus.ERROR
                    self._log.error("Failed to open resolved YouTube stream")
                    return False

                self._metadata.native_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._metadata.native_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._metadata.native_fps = self._cap.get(cv2.CAP_PROP_FPS)
                self._metadata.is_network_stream = True

                self._status = CameraStatus.ONLINE
                self._log.camera_event(
                    self._info.id,
                    "YouTube connected: %dx%d @ %.0f fps" % (
                        self._metadata.native_width,
                        self._metadata.native_height,
                        self._metadata.native_fps,
                    ),
                )
                return True

            except Exception as exc:
                self._status = CameraStatus.ERROR
                self._log.error("YouTube %s open error: %s", self._info.id, exc)
                return False

    def close(self) -> None:
        with self._lock:
            try:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                self._status = CameraStatus.OFFLINE
            except Exception as exc:
                self._log.error("YouTube %s close error: %s", self._info.id, exc)

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
            self._log.error("YouTube %s read error: %s", self._info.id, exc)
            self._status = CameraStatus.ERROR
            return None

    def reconnect(self) -> bool:
        self.close()
        return self.open()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def _resolve_stream_url(self) -> str:
        """Use yt-dlp to extract the direct stream URL."""
        quality_key = self._info.source_config.youtube_quality
        format_str = self._QUALITY_MAP.get(quality_key, self._QUALITY_MAP["best"])

        cmd = [
            "yt-dlp",
            "-f", format_str,
            "--get-url",
            "--no-warnings",
            self._info.uri,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
            self._log.warning("yt-dlp stderr: %s", result.stderr.strip())
            return ""
        except subprocess.TimeoutExpired:
            self._log.error("yt-dlp timed out for %s", self._info.id)
            return ""
        except FileNotFoundError:
            self._log.error("yt-dlp not found in PATH")
            return ""

    @staticmethod
    def _check_ytdlp() -> bool:
        return shutil.which("yt-dlp") is not None
