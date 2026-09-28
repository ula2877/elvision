from __future__ import annotations

import time
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QWidget,
    QMessageBox,
    QApplication,
)

from app.core.events.models import (
    EventRecord,
    EVENT_TYPE_COLORS,
    EVENT_STATUS_ACTIVE,
    EVENT_STATUS_ACKNOWLEDGED,
    EVENT_STATUS_RESOLVED,
    EVENT_STATUS_DISMISSED,
)
from app.core.events.manager import EventManager


class EventDetailDialog(QDialog):
    def __init__(self, event: EventRecord, manager: EventManager,
                 parent=None) -> None:
        super().__init__(parent)
        self._event = event
        self._manager = manager
        self.setWindowTitle("Event Detail")
        self.setMinimumSize(680, 540)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        content = QHBoxLayout()
        content.setSpacing(16)

        self._snapshot_label = QLabel()
        self._snapshot_label.setFixedSize(360, 270)
        self._snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snapshot_label.setStyleSheet(
            "background-color: #1E293B; border-radius: 6px; border: 1px solid #334155;"
        )
        self._load_snapshot()
        content.addWidget(self._snapshot_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(8)

        self._event_label = QLabel(self._event.event_label)
        self._event_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {EVENT_TYPE_COLORS.get(self._event.event_type, '#FFFFFF')};"
        )
        info_col.addWidget(self._event_label)

        self._camera_label = QLabel(
            f"Camera:  {self._event.camera_name or self._event.camera_id}"
        )
        self._camera_label.setStyleSheet("font-size: 13px; color: #E2E8F0;")
        info_col.addWidget(self._camera_label)

        self._group_label = QLabel(f"Group:  {self._event.group_name or '-'}")
        self._group_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        info_col.addWidget(self._group_label)

        self._time_label = QLabel(
            f"Time:  {time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self._event.timestamp))}"
        )
        self._time_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        info_col.addWidget(self._time_label)

        self._confidence_label = QLabel(
            f"Confidence:  {'{:.1%}'.format(self._event.confidence) if self._event.confidence > 0 else '-'}"
        )
        self._confidence_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        info_col.addWidget(self._confidence_label)

        self._status_label = QLabel(
            f"Status:  {self._event.status.capitalize()}"
        )
        status_color = "#10B981" if self._event.status == "new" else "#64748B"
        self._status_label.setStyleSheet(f"font-size: 13px; color: {status_color};")
        info_col.addWidget(self._status_label)

        info_col.addStretch()
        content.addLayout(info_col)
        root.addLayout(content)

        root.addWidget(QLabel("Notes:"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlainText(self._event.notes)
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.setStyleSheet(
            "background-color: #1E293B; color: #E2E8F0; border: 1px solid #334155; border-radius: 4px; padding: 4px;"
        )
        root.addWidget(self._notes_edit)

        # ── Actions ──────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._open_snapshot_btn = QPushButton("Open Snapshot")
        self._open_snapshot_btn.clicked.connect(self._open_snapshot)
        action_row.addWidget(self._open_snapshot_btn)

        self._copy_path_btn = QPushButton("Copy Snapshot Path")
        self._copy_path_btn.clicked.connect(self._copy_snapshot_path)
        action_row.addWidget(self._copy_path_btn)

        action_row.addStretch()

        rec_btn = QPushButton("Open Recording")
        rec_btn.setEnabled(False)
        action_row.addWidget(rec_btn)

        timeline_btn = QPushButton("Open Timeline")
        timeline_btn.setEnabled(False)
        action_row.addWidget(timeline_btn)

        root.addLayout(action_row)

        # ── Status management ─────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._ack_btn = QPushButton("Acknowledge")
        self._ack_btn.clicked.connect(lambda: self._update_status(EVENT_STATUS_ACKNOWLEDGED))
        btn_row.addWidget(self._ack_btn)

        self._resolve_btn = QPushButton("Resolve")
        self._resolve_btn.clicked.connect(lambda: self._update_status(EVENT_STATUS_RESOLVED))
        btn_row.addWidget(self._resolve_btn)

        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.clicked.connect(lambda: self._update_status(EVENT_STATUS_DISMISSED))
        btn_row.addWidget(self._dismiss_btn)

        btn_row.addStretch()

        save_notes_btn = QPushButton("Save Notes")
        save_notes_btn.clicked.connect(self._save_notes)
        btn_row.addWidget(save_notes_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setStyleSheet("color: #EF4444;")
        self._delete_btn.clicked.connect(self._delete_event)
        btn_row.addWidget(self._delete_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        self._update_buttons()

    def _load_snapshot(self) -> None:
        if not self._event.snapshot_path:
            self._snapshot_label.setText("No snapshot")
            return
        path = Path(self._event.snapshot_path)
        if path.exists():
            pix = QPixmap(str(path))
            scaled = pix.scaled(360, 270, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            self._snapshot_label.setPixmap(scaled)
        else:
            self._snapshot_label.setText("Snapshot not found")

    def _open_snapshot(self) -> None:
        if self._event.snapshot_path:
            path = Path(self._event.snapshot_path)
            if path.exists():
                subprocess.Popen(["start", "", str(path)], shell=True)

    def _copy_snapshot_path(self) -> None:
        if self._event.snapshot_path:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._event.snapshot_path)

    def _update_status(self, status: str) -> None:
        self._manager.update_status(self._event.id, status)
        self._event.status = status
        status_color = "#10B981" if status == "new" else "#64748B"
        self._status_label.setText(f"Status:  {status.capitalize()}")
        self._status_label.setStyleSheet(f"font-size: 13px; color: {status_color};")
        self._update_buttons()

    def _update_buttons(self) -> None:
        is_active = self._event.status in EVENT_STATUS_ACTIVE
        self._ack_btn.setEnabled(is_active)
        self._resolve_btn.setEnabled(is_active)
        self._dismiss_btn.setEnabled(is_active)

    def _save_notes(self) -> None:
        notes = self._notes_edit.toPlainText().strip()
        self._manager.update_notes(self._event.id, notes)
        self._event.notes = notes

    def _delete_event(self) -> None:
        reply = QMessageBox.question(
            self, "Delete Event",
            "Delete this event?\n\nSnapshot file will not be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_event(self._event.id)
            self.accept()
