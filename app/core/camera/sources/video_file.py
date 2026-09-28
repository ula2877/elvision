"""
VideoFileSource — local video file adapter via OpenCV.
Supports: pause, resume, loop, seek, playback speed, end-of-file detection.
"""
from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Optional

import cv2
import numpy as np

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import CameraInfo, CameraStatus, FrameData, SourceMetadata


class VideoFileSource(VideoSource):
    """Local video file source. Supports mp4, avi, mov, mkv, mpeg, wmv."""

    _SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".mpeg", ".wmv", ".flv", ".webm"}
    _RENDER_MAX_WIDTH = 640
    _RENDER_MAX_HEIGHT = 360

    def __init__(self, camera_info: CameraInfo) -> None:
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = Lock()
        self._log = LogService.instance()
        self._frame_count = 0
        self._paused = False
        self._loop = camera_info.source_config.loop
        self._speed = camera_info.source_config.playback_speed
        self._target_frame_delay: float = 1.0 / max(camera_info.fps, 1)
        self._render_frame: Optional[np.ndarray] = None

    def open(self) -> bool:
        with self._lock:
            try:
                path = Path(self._info.uri)
                if not path.exists():
                    self._status = CameraStatus.ERROR
                    self._log.error("Video file not found: %s", path)
                    return False

                if path.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
                    self._status = CameraStatus.ERROR
                    self._log.error("Unsupported video format: %s", path.suffix)
                    return False

                self._cap = cv2.VideoCapture(str(path))
                if not self._cap.isOpened():
                    self._status = CameraStatus.ERROR
                    self._log.error("Failed to open video: %s", path)
                    return False

                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self._info.source_config.buffer_size)

                self._metadata.native_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._metadata.native_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._metadata.native_fps = self._cap.get(cv2.CAP_PROP_FPS)
                self._metadata.total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
                self._metadata.is_seekable = True

                if self._metadata.native_fps > 0:
                    self._target_frame_delay = 1.0 / self._metadata.native_fps

                if self._metadata.total_frames > 0 and self._metadata.native_fps > 0:
                    self._metadata.duration_sec = self._metadata.total_frames / self._metadata.native_fps

                if self._info.source_config.seek_position_sec > 0:
                    self.seek(self._info.source_config.seek_position_sec)

                self._status = CameraStatus.ONLINE
                self._log.camera_event(
                    self._info.id,
                    "Video opened: %s (%dx%d, %.1f fps, %.1fs)" % (
                        path.name,
                        self._metadata.native_width,
                        self._metadata.native_height,
                        self._metadata.native_fps,
                        self._metadata.duration_sec,
                    ),
                )
                return True

            except Exception as exc:
                self._status = CameraStatus.ERROR
                self._log.error("Video %s open error: %s", self._info.id, exc)
                return False

    def close(self) -> None:
        with self._lock:
            try:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                self._status = CameraStatus.OFFLINE
            except Exception as exc:
                self._log.error("Video %s close error: %s", self._info.id, exc)

    def read(self) -> Optional[FrameData]:
        if self._cap is None or not self._cap.isOpened():
            return None

        try:
            if self._paused:
                time.sleep(0.01)
                return None

            ret, frame = self._cap.read()

            if not ret or frame is None:
                if self._loop:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self._frame_count = 0
                    ret, frame = self._cap.read()
                    if not ret or frame is None:
                        return None
                else:
                    self._status = CameraStatus.OFFLINE
                    return None

            self._frame_count += 1
            h, w = frame.shape[:2]

            render_w = self._RENDER_MAX_WIDTH
            render_h = self._RENDER_MAX_HEIGHT
            if w > render_w or h > render_h:
                scale = min(render_w / w, render_h / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                if self._render_frame is None or self._render_frame.shape[:2] != (new_h, new_w):
                    self._render_frame = np.empty((new_h, new_w, 3), dtype=np.uint8)
                cv2.resize(frame, (new_w, new_h), dst=self._render_frame, interpolation=cv2.INTER_AREA)
                display_frame = self._render_frame
                display_w, display_h = new_w, new_h
            else:
                display_frame = frame
                display_w, display_h = w, h

            if self._target_frame_delay > 0:
                effective_delay = self._target_frame_delay / max(self._speed, 0.1)
                time.sleep(max(0, effective_delay))

            return FrameData(
                camera_id=self._info.id,
                timestamp=time.time(),
                frame_number=self._frame_count,
                width=display_w,
                height=display_h,
                fps=float(self._metadata.native_fps),
                data=display_frame,
            )
        except Exception as exc:
            self._log.error("Video %s read error: %s", self._info.id, exc)
            self._status = CameraStatus.ERROR
            return None

    def reconnect(self) -> bool:
        self.close()
        return self.open()

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    # ── Playback controls ──────────────────────────────────────────────────────

    def pause(self) -> None:
        self._paused = True
        self._status = CameraStatus.PAUSED

    def resume(self) -> None:
        self._paused = False
        self._status = CameraStatus.ONLINE

    def toggle_pause(self) -> None:
        if self._paused:
            self.resume()
        else:
            self.pause()

    def seek(self, seconds: float) -> bool:
        if self._cap is None or not self._metadata.is_seekable:
            return False
        try:
            frame_pos = int(seconds * self._metadata.native_fps)
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            return True
        except Exception:
            return False

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.1, min(speed, 4.0))

    def set_loop(self, loop: bool) -> None:
        self._loop = loop

    @property
    def current_position_sec(self) -> float:
        if self._cap is None or self._metadata.native_fps <= 0:
            return 0.0
        frame = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
        return frame / self._metadata.native_fps

    @property
    def progress(self) -> float:
        if self._metadata.duration_sec <= 0:
            return 0.0
        return min(1.0, self.current_position_sec / self._metadata.duration_sec)

    @property
    def is_paused(self) -> bool:
        return self._paused
