"""
Configuration service — loads from JSON, YAML, or environment variables.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from app.core.logging import LogService
from app.models import AppConfig, LogLevel, ThemeMode


class ConfigService:
    """Loads and stores application configuration.
    Precedence: env vars > file > defaults.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path = config_path or Path("config.json")
        self._config = AppConfig()
        self._log = LogService.instance()

    def load(self) -> AppConfig:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
                self._apply_dict(data)
                self._log.info("Configuration loaded from %s", self._path)
            except Exception as exc:
                self._log.error("Failed to load config: %s", exc)
        self._apply_env_overrides()
        return self._config

    def save(self) -> None:
        data = {
            "theme": self._config.theme.value,
            "language": self._config.language,
            "max_cameras": self._config.max_cameras,
            "default_layout": self._config.default_layout,
            "log_level": self._config.log_level.value,
            "enable_gpu": self._config.enable_gpu,
            "hardware_accel": self._config.hardware_accel,
            "frame_buffer_size": self._config.frame_buffer_size,
            "reconnect_interval_sec": self._config.reconnect_interval_sec,
            "health_check_interval_sec": self._config.health_check_interval_sec,
            "enable_virtual_rendering": self._config.enable_virtual_rendering,
            "hidden_camera_fps": self._config.hidden_camera_fps,
            "plugins_enabled": self._config.plugins_enabled,
            "plugins_path": self._config.plugins_path,
        }
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._log.info("Configuration saved to %s", self._path)
        except Exception as exc:
            self._log.error("Failed to save config: %s", exc)

    @property
    def config(self) -> AppConfig:
        return self._config

    def update(self, **kwargs: Any) -> None:
        self._apply_dict(kwargs)
        self.save()

    def _apply_dict(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            if hasattr(self._config, key):
                if key == "theme" and isinstance(value, str):
                    try:
                        value = ThemeMode(value)
                    except ValueError:
                        continue
                elif key == "log_level" and isinstance(value, str):
                    try:
                        value = LogLevel(value)
                    except ValueError:
                        continue
                setattr(self._config, key, value)

    def _apply_env_overrides(self) -> None:
        mappings = [
            ("ELVISION_THEME", "theme", str),
            ("ELVISION_LANGUAGE", "language", str),
            ("ELVISION_MAX_CAMERAS", "max_cameras", int),
            ("ELVISION_LOG_LEVEL", "log_level", str),
            ("ELVISION_ENABLE_GPU", "enable_gpu", bool),
            ("ELVISION_FRAME_BUFFER_SIZE", "frame_buffer_size", int),
            ("ELVISION_PLUGINS_PATH", "plugins_path", str),
        ]
        for env_key, config_key, converter in mappings:
            raw = os.environ.get(env_key)
            if raw is not None:
                try:
                    val: Any = converter(raw)
                    if config_key in ("theme", "log_level"):
                        try:
                            val = ThemeMode(val) if config_key == "theme" else LogLevel(val)
                        except ValueError:
                            continue
                    setattr(self._config, config_key, val)
                except (ValueError, TypeError):
                    pass
