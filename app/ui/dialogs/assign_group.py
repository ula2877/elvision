"""
AssignGroupDialog — modal dialog for batch-assigning cameras to a group.

Shows the list of selected cameras and a group dropdown.
Default action is Cancel (safe default).

Signals:
    group_assigned(str) — emitted with the chosen group_id (empty string = ungroup)
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QComboBox,
    QScrollArea,
    QWidget,
)

from app.models import CameraInfo


class AssignGroupDialog(QDialog):
    """Modal dialog for assigning one or more cameras to a group.

    Shows:
        - Title
        - List of selected cameras
        - Group dropdown (None + user groups)
        - Cancel / Assign buttons (Cancel is default)
    """

    group_assigned = Signal(str)  # group_id (empty string = ungroup)

    def __init__(
        self,
        cameras: list[CameraInfo],
        groups: list[tuple[str, str]],  # [(group_id, group_name), ...]
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign Cameras To Group")
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
        self.setMinimumHeight(300)
        self.setModal(True)
        self._cameras = cameras
        self._groups = groups
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1A1D27; }"
            "QLabel { color: #E2E8F0; font-size: 12px; background: transparent; }"
            "QComboBox { background-color: #2A2D3A; border: 1px solid #2E3140; "
            "border-radius: 6px; padding: 6px 10px; color: #E2E8F0; font-size: 12px; }"
            "QComboBox:focus { border-color: #3B82F6; }"
            "QPushButton#primary { background-color: #3B82F6; color: white; "
            "border: none; border-radius: 6px; padding: 8px 24px; font-weight: 600; "
            "font-size: 12px; }"
            "QPushButton#primary:hover { background-color: #2563EB; }"
            "QPushButton#cancel { background: transparent; border: 1px solid #2E3140; "
            "color: #8892A4; border-radius: 6px; padding: 8px 24px; font-size: 12px; }"
            "QPushButton#cancel:hover { border-color: #E2E8F0; color: #E2E8F0; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Title ───────────────────────────────────────
        title = QLabel("Assign Cameras To Group")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #E2E8F0; background: transparent;"
        )
        root.addWidget(title)

        # ── Count ───────────────────────────────────────
        count = len(self._cameras)
        count_text = (
            "Selected %d camera%s:"
            % (count, "s" if count != 1 else "")
        )
        count_label = QLabel(count_text)
        count_label.setStyleSheet(
            "color: #8892A4; font-size: 12px; background: transparent;"
        )
        root.addWidget(count_label)

        # ── Camera list ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #2E3140; border-radius: 6px; "
            "background: #21242F; }"
        )

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(12, 8, 12, 8)
        list_layout.setSpacing(4)

        for info in self._cameras:
            row = QLabel(
                '<span style="color: #E2E8F0; font-size: 12px; font-weight: 500;">%s</span>  '
                '<span style="color: #8892A4; font-size: 10px;">%s</span>'
                % (info.name, info.source_type.display_name)
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setFixedHeight(28)
            list_layout.addWidget(row)

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        root.addWidget(scroll, 1)

        # ── Group selector ──────────────────────────────
        group_row = QHBoxLayout()
        group_label = QLabel("Group:")
        group_label.setStyleSheet(
            "color: #E2E8F0; font-size: 12px; font-weight: 500; background: transparent;"
        )
        group_row.addWidget(group_label)

        self._group_combo = QComboBox()
        self._group_combo.addItem("None (Ungroup)", "")
        for gid, gname in self._groups:
            self._group_combo.addItem(gname, gid)
        self._group_combo.setMinimumWidth(200)
        group_row.addWidget(self._group_combo, 1)
        group_row.addStretch()

        root.addLayout(group_row)

        # ── Info hint ───────────────────────────────────
        hint = QLabel("Cameras will be moved from their current group to the selected group.")
        hint.setStyleSheet(
            "color: #8892A4; font-size: 11px; font-style: italic; background: transparent;"
        )
        root.addWidget(hint)

        # ── Buttons ─────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        assign_btn = QPushButton("Assign")
        assign_btn.setObjectName("primary")
        assign_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        assign_btn.clicked.connect(self._on_assign)
        btn_layout.addWidget(assign_btn)

        root.addLayout(btn_layout)

    def _on_assign(self) -> None:
        group_id = self._group_combo.currentData() or ""
        self.group_assigned.emit(group_id)
        self.accept()
