"""
CreateGroupDialog / EditGroupDialog — modal dialogs for group management.

Signals:
    group_created(CameraGroup)   — emitted after successful creation
    group_edited(CameraGroup)    — emitted after successful edit
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFormLayout,
    QMessageBox,
    QWidget,
)

from app.models import CameraGroup


_DIALOG_STYLE = (
    "QDialog { background-color: #1A1D27; }"
    "QLabel { color: #E2E8F0; font-size: 12px; background: transparent;}"
    "QLineEdit, QTextEdit { background-color: #2A2D3A; "
    "border: 1px solid #2E3140; border-radius: 6px; padding: 6px 10px; "
    "color: #E2E8F0; font-size: 12px; }"
    "QLineEdit:focus, QTextEdit:focus { border-color: #3B82F6; }"
    "QPushButton#primary { background-color: #3B82F6; color: white; "
    "border: none; border-radius: 6px; padding: 8px 20px; font-weight: 600; }"
    "QPushButton#primary:hover { background-color: #2563EB; }"
    "QPushButton#cancel { background: transparent; border: 1px solid #2E3140; "
    "color: #8892A4; border-radius: 6px; padding: 8px 20px; }"
    "QPushButton#cancel:hover { border-color: #E2E8F0; color: #E2E8F0; }"
)


class CreateGroupDialog(QDialog):
    """Modal dialog for creating a new camera group.

    Usage:
        dlg = CreateGroupDialog(parent)
        dlg.group_created.connect(handler)
    """

    group_created = Signal(object)  # CameraGroup

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Camera Group")
        self.setMinimumSize(420, 280)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Create Camera Group")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #E2E8F0;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Traffic Cameras")
        form.addRow("Group Name:", self._name_input)

        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText("Optional description...")
        self._desc_input.setFixedHeight(80)
        form.addRow("Description:", self._desc_input)

        root.addLayout(form)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self._create_btn = QPushButton("Create")
        self._create_btn.setObjectName("primary")
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._create_btn)

        root.addLayout(btn_layout)

        self._name_input.setFocus()

    def _on_submit(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Group name cannot be empty.")
            return
        desc = self._desc_input.toPlainText().strip()
        self.group_created.emit(
            CameraGroup(id="", name=name, description=desc)
        )
        self.accept()


class EditGroupDialog(QDialog):
    """Modal dialog for editing an existing camera group.

    Usage:
        dlg = EditGroupDialog(group, parent)
        dlg.group_edited.connect(handler)
    """

    group_edited = Signal(object)  # CameraGroup

    def __init__(
        self,
        group: CameraGroup,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._group = group
        self.setWindowTitle("Edit Group — %s" % group.name)
        self.setMinimumSize(420, 280)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Edit Group")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #E2E8F0;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Traffic Cameras")
        form.addRow("Group Name:", self._name_input)

        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText("Optional description...")
        self._desc_input.setFixedHeight(80)
        form.addRow("Description:", self._desc_input)

        root.addLayout(form)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setObjectName("primary")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._save_btn)

        root.addLayout(btn_layout)

        self._name_input.setFocus()

    def _populate(self) -> None:
        self._name_input.setText(self._group.name)
        self._desc_input.setPlainText(self._group.description)

    def _on_submit(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Group name cannot be empty.")
            return
        desc = self._desc_input.toPlainText().strip()
        updated = CameraGroup(
            id=self._group.id,
            name=name,
            description=desc,
            parent_id=self._group.parent_id,
            children_ids=list(self._group.children_ids),
            camera_ids=list(self._group.camera_ids),
            icon=self._group.icon,
            color=self._group.color,
            is_favorite=self._group.is_favorite,
            created_at=self._group.created_at,
            updated_at=self._group.updated_at,
            metadata=dict(self._group.metadata),
        )
        self.group_edited.emit(updated)
        self.accept()
