"""
Elvision — Video Management System
Entry point.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.core.configuration import ConfigService
from app.core.logging import LogService
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Smart Elvision")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Elvision")
    app.setStyle("Fusion")

    config_service = ConfigService(Path("config.json"))
    config = config_service.load()

    log_service = LogService.instance(config.log_level)
    log_service.info("Elvision starting...")

    window = MainWindow(config_service)
    window.showMaximized()

    log_service.info("Elvision ready")

    result = app.exec()

    log_service.info("Elvision shutting down (exit code: %d)", result)
    return result


if __name__ == "__main__":
    sys.exit(main())
