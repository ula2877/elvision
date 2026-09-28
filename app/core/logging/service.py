"""
Core logging service — centralized, structured, async-capable.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from app.models import LogLevel


class LogService:
    """Central logging service.
    Wraps Python's logging module and adds structured fields.
    """

    _instance: Optional[LogService] = None

    def __init__(self, level: LogLevel = LogLevel.INFO) -> None:
        self._logger = logging.getLogger("elvision")
        self._logger.setLevel(self._to_python_level(level))

        fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stdout = logging.StreamHandler(sys.stdout)
        stdout.setFormatter(fmt)
        self._logger.addHandler(stdout)

        self._file_handler: Optional[logging.FileHandler] = None

    @classmethod
    def instance(cls, level: LogLevel = LogLevel.INFO) -> LogService:
        if cls._instance is None:
            cls._instance = cls(level)
        return cls._instance

    def set_file_output(self, path: Path) -> None:
        if self._file_handler is not None:
            self._logger.removeHandler(self._file_handler)
        self._file_handler = logging.FileHandler(path, encoding="utf-8")
        self._file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._logger.addHandler(self._file_handler)

    def set_level(self, level: LogLevel) -> None:
        self._logger.setLevel(self._to_python_level(level))

    def debug(self, msg: str, *args: object, **extra: object) -> None:
        self._logger.debug(msg, *args, extra={"extra": extra})

    def info(self, msg: str, *args: object, **extra: object) -> None:
        self._logger.info(msg, *args, extra={"extra": extra})

    def warning(self, msg: str, *args: object, **extra: object) -> None:
        self._logger.warning(msg, *args, extra={"extra": extra})

    def error(self, msg: str, *args: object, **extra: object) -> None:
        self._logger.error(msg, *args, extra={"extra": extra})

    def critical(self, msg: str, *args: object, **extra: object) -> None:
        self._logger.critical(msg, *args, extra={"extra": extra})

    def camera_event(self, camera_id: str, event: str, **extra: object) -> None:
        self._logger.info("[CAMERA %s] %s", camera_id, event, extra={"extra": extra})

    def performance(self, label: str, duration_ms: float, **extra: object) -> None:
        self._logger.debug(
            "[PERF] %s took %.1f ms", label, duration_ms, extra={"extra": extra}
        )

    @staticmethod
    def _to_python_level(level: LogLevel) -> int:
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(level, logging.INFO)
