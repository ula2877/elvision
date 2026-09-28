"""
Settings service — global and per-camera settings with JSON persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.core.logging import LogService
from app.models import AppConfig


class SettingsService:
    """Manages user settings with JSON persistence."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or Path("settings.json")
        self._data: dict[str, Any] = {}
        self._log = LogService.instance()
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def get_camera_setting(self, camera_id: str, key: str, default: Any = None) -> Any:
        cam = self._data.setdefault("cameras", {})
        cam_settings = cam.setdefault(camera_id, {})
        return cam_settings.get(key, default)

    def set_camera_setting(self, camera_id: str, key: str, value: Any) -> None:
        cam = self._data.setdefault("cameras", {})
        cam_settings = cam.setdefault(camera_id, {})
        cam_settings[key] = value
        self._save()

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
                self._log.info("Settings loaded from %s", self._path)
        except Exception as exc:
            self._log.error("Failed to load settings: %s", exc)
            self._data = {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as exc:
            self._log.error("Failed to save settings: %s", exc)
