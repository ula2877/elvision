from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import cv2

from app.core.logging import LogService


_SNAPSHOT_ROOT = Path("data/snapshots")


class EventSnapshotter:
    def __init__(self, root_dir: str | Path = _SNAPSHOT_ROOT) -> None:
        self._root = Path(root_dir)
        self._log = LogService.instance()
        self._lock = threading.Lock()

    def save(self, frame: np.ndarray, event_type: str,
             camera_id: str, timestamp: float) -> Optional[Path]:
        try:
            dt = time.gmtime(timestamp)
            date_str = time.strftime("%Y%m%d", dt)
            time_str = time.strftime("%Y%m%d_%H%M%S", dt)

            subdir = self._root / date_str / event_type
            subdir.mkdir(parents=True, exist_ok=True)

            filename = f"{time_str}_{camera_id}.jpg"
            path = subdir / filename

            with self._lock:
                cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            self._log.info("Event snapshot saved: %s", path)
            return path
        except Exception as exc:
            self._log.error("Failed to save event snapshot: %s", exc)
            return None
