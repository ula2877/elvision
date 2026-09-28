"""
Snapshot service — async, non-blocking image capture.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.core.logging import LogService
from app.models import SnapshotRequest


class SnapshotService:
    """Handles screenshot / snapshot capture independently of camera or UI."""

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._output_dir = output_dir or Path("snapshots")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._log = LogService.instance()

    def save_frame(
        self,
        frame: np.ndarray,
        camera_id: str,
        fmt: str = "jpg",
        quality: int = 95,
    ) -> Optional[Path]:
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{camera_id}_{ts}.{fmt}"
            path = self._output_dir / filename

            if fmt == "jpg":
                cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            elif fmt == "png":
                cv2.imwrite(str(path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            else:
                cv2.imwrite(str(path), frame)

            self._log.info("Snapshot saved: %s (%dx%d)", path, frame.shape[1], frame.shape[0])
            return path
        except Exception as exc:
            self._log.error("Snapshot failed for %s: %s", camera_id, exc)
            return None
