"""
ModelLoader — singleton YOLO model cache.

Loads one Ultralytics YOLO model per unique path and reuses it across
all workers that need the same model.  The first call for a given path
triggers the download (if not cached locally); subsequent calls return
the already-loaded model instantly.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.core.logging import LogService


class ModelLoader:
    """Thread-safe singleton that caches YOLO model instances."""

    _instance: Optional[ModelLoader] = None
    _lock_class = threading.Lock()

    def __new__(cls) -> ModelLoader:
        if cls._instance is None:
            with cls._lock_class:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._models = {}
                    cls._instance._models_lock = threading.Lock()
                    cls._instance._log = LogService.instance()
        return cls._instance

    def get_model(self, model_path: str = "app/core/ai/weights/fall_detection/best.pt"):
        """Return a cached YOLO model, loading it on first access.

        Args:
            model_path: Path or name of the YOLO model file
                        (e.g. ``"app/core/ai/weights/fall_detection/best.pt"``, ``"yolov8n.pt"``).
                        Ultralytics will download the file automatically
                        when it is not found locally.

        Returns:
            An ``ultralytics.YOLO`` instance.
        """
        with self._models_lock:
            if model_path not in self._models:
                self._log.info("Loading YOLO model: %s", model_path)
                try:
                    from ultralytics import YOLO

                    self._models[model_path] = YOLO(model_path)
                    self._log.info("YOLO model loaded: %s", model_path)
                except ImportError:
                    self._log.error(
                        "ultralytics is not installed. "
                        "Install it with: pip install ultralytics"
                    )
                    raise
            return self._models[model_path]

    def unload(self, model_path: str) -> None:
        """Remove a cached model from memory."""
        with self._models_lock:
            self._models.pop(model_path, None)

    def unload_all(self) -> None:
        """Remove all cached models from memory."""
        with self._models_lock:
            self._models.clear()
