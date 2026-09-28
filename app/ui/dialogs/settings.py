"""
SettingsDialog — application settings with tabbed interface.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QWidget,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QLineEdit,
    QFrame,
)

from app.models import AppConfig, ThemeMode, LogLevel


class SettingsDialog(QDialog):
    """Application settings dialog with tabs."""

    settings_saved = Signal(dict)  # changed settings

    def __init__(
        self,
        config: AppConfig,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 480)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1A1D27; }"
            "QLabel { color: #E2E8F0; font-size: 12px; }"
            "QComboBox, QSpinBox, QLineEdit { background-color: #2A2D3A; "
            "border: 1px solid #2E3140; border-radius: 6px; padding: 5px 10px; "
            "color: #E2E8F0; }"
            "QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border-color: #3B82F6; }"
            "QCheckBox { color: #E2E8F0; spacing: 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; "
            "border: 1px solid #2E3140; background: #2A2D3A; }"
            "QCheckBox::indicator:checked { background: #3B82F6; border-color: #3B82F6; }"
            "QTabWidget::pane { border: 1px solid #2E3140; border-radius: 6px; background: #1A1D27; }"
            "QTabBar::tab { background: #21242F; border: 1px solid #2E3140; "
            "border-bottom: none; padding: 8px 16px; color: #8892A4; "
            "border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }"
            "QTabBar::tab:selected { background: #1A1D27; color: #E2E8F0; "
            "border-bottom: 2px solid #3B82F6; }"
            "QPushButton#primary { background-color: #3B82F6; color: white; "
            "border: none; border-radius: 6px; padding: 8px 24px; font-weight: 600; }"
            "QPushButton#primary:hover { background-color: #2563EB; }"
            "QPushButton#cancel { background: transparent; border: 1px solid #2E3140; "
            "color: #8892A4; border-radius: 6px; padding: 8px 24px; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._performance_tab(), "Performance")
        tabs.addTab(self._recording_tab(), "Recording")
        tabs.addTab(self._network_tab(), "Network")
        root.addWidget(tabs)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        root.addLayout(btn_layout)

    def _general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._theme_combo = QComboBox()
        for t in ThemeMode:
            self._theme_combo.addItem(t.value.title(), t.value)
        self._theme_combo.setCurrentText(self._config.theme.value)
        form.addRow("Theme:", self._theme_combo)

        self._lang_combo = QComboBox()
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Bahasa Indonesia", "id")
        self._lang_combo.setCurrentText(self._config.language)
        form.addRow("Language:", self._lang_combo)

        self._log_level_combo = QComboBox()
        for level in LogLevel:
            self._log_level_combo.addItem(level.value.upper(), level.value)
        self._log_level_combo.setCurrentText(self._config.log_level.value)
        form.addRow("Log Level:", self._log_level_combo)

        self._plugins_check = QCheckBox("Enable Plugins")
        self._plugins_check.setChecked(self._config.plugins_enabled)
        form.addRow("", self._plugins_check)

        return w

    def _performance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._max_cameras_spin = QSpinBox()
        self._max_cameras_spin.setRange(1, 256)
        self._max_cameras_spin.setValue(self._config.max_cameras)
        form.addRow("Max Cameras:", self._max_cameras_spin)

        self._frame_buffer_spin = QSpinBox()
        self._frame_buffer_spin.setRange(1, 60)
        self._frame_buffer_spin.setValue(self._config.frame_buffer_size)
        form.addRow("Frame Buffer Size:", self._frame_buffer_spin)

        self._gpu_check = QCheckBox("Enable GPU Acceleration")
        self._gpu_check.setChecked(self._config.enable_gpu)
        form.addRow("", self._gpu_check)

        self._virtual_render_check = QCheckBox("Virtual Camera Rendering")
        self._virtual_render_check.setChecked(self._config.enable_virtual_rendering)
        form.addRow("", self._virtual_render_check)

        self._hidden_fps_spin = QSpinBox()
        self._hidden_fps_spin.setRange(1, 15)
        self._hidden_fps_spin.setValue(self._config.hidden_camera_fps)
        form.addRow("Hidden Camera FPS:", self._hidden_fps_spin)

        return w

    def _recording_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._rec_path = QLineEdit()
        self._rec_path.setPlaceholderText("./recordings")
        form.addRow("Recording Path:", self._rec_path)

        self._rec_format = QComboBox()
        self._rec_format.addItems(["MP4", "AVI", "MKV"])
        form.addRow("Format:", self._rec_format)

        return w

    def _network_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self._reconnect_spin = QSpinBox()
        self._reconnect_spin.setRange(1, 60)
        self._reconnect_spin.setValue(int(self._config.reconnect_interval_sec))
        self._reconnect_spin.setSuffix(" sec")
        form.addRow("Reconnect Interval:", self._reconnect_spin)

        self._health_spin = QSpinBox()
        self._health_spin.setRange(5, 120)
        self._health_spin.setValue(int(self._config.health_check_interval_sec))
        self._health_spin.setSuffix(" sec")
        form.addRow("Health Check Interval:", self._health_spin)

        return w

    def _on_save(self) -> None:
        changes = {
            "theme": self._theme_combo.currentData(),
            "language": self._lang_combo.currentData(),
            "log_level": self._log_level_combo.currentData(),
            "plugins_enabled": self._plugins_check.isChecked(),
            "max_cameras": self._max_cameras_spin.value(),
            "frame_buffer_size": self._frame_buffer_spin.value(),
            "enable_gpu": self._gpu_check.isChecked(),
            "enable_virtual_rendering": self._virtual_render_check.isChecked(),
            "hidden_camera_fps": self._hidden_fps_spin.value(),
            "reconnect_interval_sec": float(self._reconnect_spin.value()),
            "health_check_interval_sec": float(self._health_spin.value()),
        }
        self.settings_saved.emit(changes)
        self.accept()
