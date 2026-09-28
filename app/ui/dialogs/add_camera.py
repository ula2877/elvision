"""
AddCameraDialog / EditCameraDialog — modal dialog for adding or editing a camera source.

Supports two modes:
    Mode.ADD   — create a new camera with a new UUID
    Mode.EDIT  — populate from an existing CameraInfo; non-editable fields preserved

Signals:
    camera_added(CameraInfo)   — emitted in ADD mode
    camera_edited(CameraInfo)  — emitted in EDIT mode (includes original id/source_config)
"""
from __future__ import annotations

import enum
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QPushButton,
    QFrame,
    QFormLayout,
    QMessageBox,
    QDoubleSpinBox,
    QCheckBox,
    QStackedWidget,
    QWidget,
    QSizePolicy,
    QScrollArea,
)

from app.models import CameraInfo, SourceType, SourceConfig, TransportProtocol
from app.core.ai.registry import AIFeatureRegistry


_GROUP_SHEET = """
QScrollArea {
    border: none;
    background: transparent;
}
QWidget#connectionContent {
    background: #21242F;
}
QWidget#featureContainer {
    background: #21242F;
}
QWidget#advancedContent {
    background: #21242F;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #4B5563;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #6B7280;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
}
"""


class GroupSelection:
    __slots__ = ("group_id",)

    def __init__(self, group_id: Optional[str] = None) -> None:
        self.group_id = group_id


class DialogMode(enum.Enum):
    ADD = "add"
    EDIT = "edit"


# ── Collapsible section widget ───────────────────────────────────────────────


class _CollapsibleSection(QWidget):
    """A header bar that toggles visibility of its content widget."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._content = content
        self._checked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = QPushButton()
        self._header.setCheckable(True)
        self._header.setChecked(False)
        self._header.setStyleSheet(
            "QPushButton { text-align: left; border: none; border-radius: 0; "
            "padding: 8px 12px; font-size: 12px; font-weight: 600; "
            "color: #E2E8F0; background: #2A2D3A; }"
            "QPushButton:hover { background: #353849; }"
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        root.addWidget(self._header)

        self._content.setVisible(False)
        root.addWidget(self._content)

        self._update_title(title, 0)

    def _update_title(self, title: str, count: int) -> None:
        arrow = "\u25BC" if self._checked else "\u25B6"
        badge = f"  ({count} Enabled)" if count > 0 else ""
        self._header.setText(f"  {arrow}  {title}{badge}")

    def set_title(self, title: str, count: int = 0) -> None:
        self._update_title(title, count)

    def _toggle(self) -> None:
        self._checked = not self._checked
        self._content.setVisible(self._checked)
        self.setFixedHeight(self.sizeHint().height() if self._checked else 38)
        parent = self.parentWidget()
        if parent:
            parent.adjustSize()
            parent.updateGeometry()

    def expand(self) -> None:
        if not self._checked:
            self._toggle()

    def collapse(self) -> None:
        if self._checked:
            self._toggle()


# ── Inline collapsible for Advanced Connection ────────────────────────────────


class _InlineCollapsible(QWidget):
    """Collapsible row inside a form layout — shows a toggle header + content."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._content = content
        self._expanded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = QPushButton()
        self._header.setCheckable(True)
        self._header.setChecked(False)
        self._header.setStyleSheet(
            "QPushButton { text-align: left; border: none; border-radius: 0; "
            "padding: 6px 2px; font-size: 11px; font-weight: 600; "
            "color: #60A5FA; background: transparent; }"
            "QPushButton:hover { color: #93C5FD; }"
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        root.addWidget(self._header)

        self._content.setVisible(False)
        root.addWidget(self._content)

        self._set_label(title)

    def _set_label(self, title: str) -> None:
        arrow = "\u25BC" if self._expanded else "\u25B6"
        self._header.setText(f"{arrow}  {title}")

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._set_label(self._header.text().lstrip("\u25B6\u25BC ").strip().lstrip())
        p = self.parentWidget()
        if p:
            p.adjustSize()
            p.updateGeometry()

    def expand(self) -> None:
        if not self._expanded:
            self._toggle()

    def collapse(self) -> None:
        if self._expanded:
            self._toggle()


# ── Main dialog ──────────────────────────────────────────────────────────────


class AddCameraDialog(QDialog):
    """Modal dialog for adding or editing a camera / video source.

    Usage:
        # Add mode
        dlg = AddCameraDialog(parent)
        dlg.camera_added.connect(handler)

        # Edit mode — populate from existing CameraInfo
        dlg = AddCameraDialog(parent, mode=DialogMode.EDIT, camera_info=info,
                              groups=[("group_id", "Group Name"), ...])
        dlg.camera_edited.connect(handler)
    """

    camera_added = Signal(object)
    camera_edited = Signal(object)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        mode: DialogMode = DialogMode.ADD,
        camera_info: Optional[CameraInfo] = None,
        groups: Optional[list[tuple[str, str]]] = None,
        current_group_id: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._edit_info = camera_info
        self._groups = groups or []
        self._current_group_id = current_group_id
        self.setMinimumSize(720, 640)
        self.setModal(True)
        self._category_sections: dict[str, _CollapsibleSection] = {}
        self._category_checks: dict[str, list[QCheckBox]] = {}
        self._build_ui()
        self._apply_mode()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #1A1D27; }"
            "QLabel { color: #E2E8F0; font-size: 12px; background: transparent;}"
            "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background-color: #2A2D3A; "
            "border: 1px solid #2E3140; border-radius: 6px; padding: 6px 10px; "
            "color: #E2E8F0; font-size: 12px; }"
            "QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #3B82F6; }"
            "QCheckBox { color: #E2E8F0; spacing: 8px; background: transparent;}"
            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; "
            "border: 1px solid #2E3140; background: #2A2D3A; }"
            "QCheckBox::indicator:checked { background: #3B82F6; border-color: #3B82F6; }"
            "QPushButton#primary { background-color: #3B82F6; color: white; "
            "border: none; border-radius: 6px; padding: 8px 20px; font-weight: 600; }"
            "QPushButton#primary:hover { background-color: #2563EB; }"
            "QPushButton#cancel { background: transparent; border: 1px solid #2E3140; "
            "color: #8892A4; border-radius: 6px; padding: 8px 20px; }"
            "QPushButton#cancel:hover { border-color: #E2E8F0; color: #E2E8F0; }"
            "QFrame#section { background: #21242F; border: 1px solid #2E3140; border-radius: 8px; padding: 12px; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # Title
        self._title = QLabel("Add New Source")
        self._title.setStyleSheet("font-size: 18px; font-weight: 700; color: #E2E8F0;")
        root.addWidget(self._title)

        # Two-column body
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # ── Left column: General (static, no scroll) ──────────────────────────
        left_frame = QFrame()
        left_frame.setObjectName("section")
        left_form = QFormLayout(left_frame)
        left_form.setSpacing(10)
        left_form.setContentsMargins(12, 12, 12, 12)

        left_hdr = QLabel("General")
        left_hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #60A5FA; margin-bottom: 4px;")
        left_form.addRow(left_hdr)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Front Entrance Camera")
        left_form.addRow("Name:", self._name_input)

        self._location_input = QLineEdit()
        self._location_input.setPlaceholderText("e.g. Building A, Floor 1")
        left_form.addRow("Location:", self._location_input)

        self._group_combo = QComboBox()
        self._group_combo.addItem("None (Ungrouped)", "")
        for gid, gname in self._groups:
            self._group_combo.addItem(gname, gid)
        self._group_combo.setVisible(False)
        self._group_label = QLabel("Group:")
        self._group_label.setVisible(False)
        left_form.addRow(self._group_label, self._group_combo)

        columns.addWidget(left_frame)

        # ── Right column: Connection (scrollable) ─────────────────────────────
        right_frame = QFrame()
        right_frame.setObjectName("section")
        right_outer = QVBoxLayout(right_frame)
        right_outer.setContentsMargins(0, 0, 0, 0)
        right_outer.setSpacing(0)

        right_hdr = QLabel("  Connection")
        right_hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #60A5FA; padding: 12px 12px 4px 12px;")
        right_outer.addWidget(right_hdr)

        conn_scroll = QScrollArea()
        conn_scroll.setWidgetResizable(True)
        conn_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        conn_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conn_scroll.setStyleSheet(_GROUP_SHEET)

        conn_inner = QWidget()
        conn_inner.setObjectName("connectionContent")
        conn_form = QFormLayout(conn_inner)
        conn_form.setSpacing(10)
        conn_form.setContentsMargins(12, 4, 12, 12)

        self._type_combo = QComboBox()
        for st in SourceType:
            self._type_combo.addItem(st.display_name, st.value)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        conn_form.addRow("Source Type:", self._type_combo)

        self._uri_input = QLineEdit()
        self._uri_input.setPlaceholderText("rtsp://192.168.1.100:554/stream")
        conn_form.addRow("URL / Address:", self._uri_input)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("admin")
        conn_form.addRow("Username:", self._username_input)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("password")
        conn_form.addRow("Password:", self._password_input)

        # ── Advanced Connection (collapsible, inside scroll) ───────────────────
        adv_content = QWidget()
        adv_content.setObjectName("advancedContent")
        adv_form = QFormLayout(adv_content)
        adv_form.setSpacing(8)
        adv_form.setContentsMargins(0, 6, 0, 0)

        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 120)
        self._fps_spin.setValue(30)
        adv_form.addRow("FPS:", self._fps_spin)

        self._transport_combo = QComboBox()
        for tp in TransportProtocol:
            self._transport_combo.addItem(tp.value.upper(), tp.value)
        adv_form.addRow("Transport:", self._transport_combo)

        self._reconnect_check = QCheckBox("Auto Reconnect")
        self._reconnect_check.setChecked(True)
        adv_form.addRow("", self._reconnect_check)

        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["Best", "1080p", "720p", "480p"])
        adv_form.addRow("YT Quality:", self._quality_combo)

        self._adv_section = _InlineCollapsible("Advanced Connection", adv_content)
        conn_form.addRow(self._adv_section)

        conn_scroll.setWidget(conn_inner)
        right_outer.addWidget(conn_scroll)

        columns.addWidget(right_frame)

        root.addLayout(columns)

        # ── AI Features (scrollable, fixed height) ────────────────────────────
        feat_frame = QFrame()
        feat_frame.setObjectName("section")
        feat_outer = QVBoxLayout(feat_frame)
        feat_outer.setContentsMargins(0, 0, 0, 0)
        feat_outer.setSpacing(0)

        feat_hdr = QLabel("  AI Features")
        feat_hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #60A5FA; padding: 12px 12px 4px 12px;")
        feat_outer.addWidget(feat_hdr)

        feat_scroll = QScrollArea()
        feat_scroll.setWidgetResizable(True)
        feat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        feat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        feat_scroll.setFixedHeight(240)
        feat_scroll.setStyleSheet(_GROUP_SHEET)

        self._features_container = QWidget()
        self._features_container.setObjectName("featureContainer")
        self._features_layout = QVBoxLayout(self._features_container)
        self._features_layout.setContentsMargins(4, 4, 4, 4)
        self._features_layout.setSpacing(0)
        self._build_feature_sections()
        self._features_layout.addStretch()

        feat_scroll.setWidget(self._features_container)
        feat_outer.addWidget(feat_scroll)

        root.addWidget(feat_frame)

        # ── Buttons ───────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2E3140;")
        root.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("cancel")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._action_btn = QPushButton("Add Source")
        self._action_btn.setObjectName("primary")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._action_btn)

        root.addLayout(btn_layout)

        self._on_type_changed(0)

    # ── Feature sections ──────────────────────────────────────────────────────

    def _build_feature_sections(self) -> None:
        grouped = AIFeatureRegistry.by_category()
        for category, features in grouped.items():
            content = QWidget()
            content_lay = QVBoxLayout(content)
            content_lay.setContentsMargins(20, 4, 4, 4)
            content_lay.setSpacing(2)

            checks: list[QCheckBox] = []
            for feat in features:
                label = feat.name if feat.available else f"{feat.name} (Coming Soon)"
                cb = QCheckBox(label)
                cb.setProperty("feature_key", feat.key)
                if not feat.available:
                    cb.setEnabled(False)
                    cb.setToolTip("This AI feature is not available in the current version.")
                checks.append(cb)
                content_lay.addWidget(cb)

            self._category_checks[category] = checks

            section = _CollapsibleSection(category, content, self._features_container)
            self._category_sections[category] = section
            self._features_layout.addWidget(section)

    def _refresh_section_counts(self) -> None:
        for category, checks in self._category_checks.items():
            count = sum(1 for cb in checks if cb.isChecked())
            if category in self._category_sections:
                self._category_sections[category].set_title(category, count)

    # ── Mode handling ─────────────────────────────────────────────────────────

    def _apply_mode(self) -> None:
        if self._mode == DialogMode.EDIT and self._edit_info is not None:
            self.setWindowTitle("Edit Camera")
            self._title.setText("Edit Camera")
            self._action_btn.setText("Save Changes")
            self._populate_from_info(self._edit_info)
            self._group_combo.setVisible(True)
            self._group_label.setVisible(True)
            self._select_group(self._current_group_id)
        else:
            self.setWindowTitle("Add Source")
            self._title.setText("Add New Source")
            self._action_btn.setText("Add Source")

    def _populate_from_info(self, info: CameraInfo) -> None:
        self._name_input.setText(info.name)
        self._uri_input.setText(info.uri)
        self._location_input.setText(info.location)
        self._username_input.setText(info.username)
        self._password_input.setText(info.password)
        self._fps_spin.setValue(info.fps)
        self._reconnect_check.setChecked(info.auto_reconnect)

        type_index = self._type_combo.findData(info.source_type.value)
        if type_index >= 0:
            self._type_combo.setCurrentIndex(type_index)

        tp_index = self._transport_combo.findData(info.source_config.transport_protocol.value)
        if tp_index >= 0:
            self._transport_combo.setCurrentIndex(tp_index)

        if info.source_type == SourceType.YOUTUBE:
            quality = info.source_config.youtube_quality.capitalize()
            q_index = self._quality_combo.findText(quality)
            if q_index >= 0:
                self._quality_combo.setCurrentIndex(q_index)

        self._set_selected_features(info.enabled_features)

    def _select_group(self, group_id: Optional[str]) -> None:
        if group_id:
            idx = self._group_combo.findData(group_id)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)
                return
        self._group_combo.setCurrentIndex(0)

    # ── Feature helpers ───────────────────────────────────────────────────────

    def _get_selected_features(self) -> list[str]:
        selected = []
        for checks in self._category_checks.values():
            for cb in checks:
                if cb.isChecked():
                    key = cb.property("feature_key")
                    if key:
                        selected.append(key)
        return selected

    def _set_selected_features(self, features: list[str]) -> None:
        feature_set = set(features)
        for checks in self._category_checks.values():
            for cb in checks:
                key = cb.property("feature_key")
                if key and key in feature_set:
                    cb.setChecked(True)
        self._refresh_section_counts()

    # ── Type change ───────────────────────────────────────────────────────────

    def _on_type_changed(self, index: int) -> None:
        source_type_value = self._type_combo.currentData()
        try:
            source_type = SourceType(source_type_value)
        except ValueError:
            return

        placeholders = {
            SourceType.WEBCAM: "0 (device index)",
            SourceType.VIDEO_FILE: "/path/to/video.mp4",
            SourceType.RTSP: "rtsp://192.168.1.100:554/stream",
            SourceType.HLS: "https://example.com/live/index.m3u8",
            SourceType.YOUTUBE: "https://youtube.com/watch?v=...",
            SourceType.NETWORK_STREAM: "https://camera/live",
            SourceType.IP_CAMERA: "rtsp://192.168.1.100:554/stream",
            SourceType.ONVIF: "http://192.168.1.100/onvif/device_service",
        }
        self._uri_input.setPlaceholderText(
            placeholders.get(source_type, "Enter URL")
        )

        from app.models import get_source_capabilities

        caps = get_source_capabilities(source_type)
        self._username_input.setVisible(caps.requires_auth)
        self._password_input.setVisible(caps.requires_auth)

    # ── Submit ────────────────────────────────────────────────────────────────

    def _on_submit(self) -> None:
        name = self._name_input.text().strip()
        uri = self._uri_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not uri:
            QMessageBox.warning(self, "Validation", "URL / Address is required.")
            return

        source_type_value = self._type_combo.currentData()
        source_type = SourceType(source_type_value)
        transport_value = self._transport_combo.currentData()
        quality_text = self._quality_combo.currentText().lower()

        if self._mode == DialogMode.EDIT and self._edit_info is not None:
            camera_id = self._edit_info.id
            source_config = self._edit_info.source_config
            source_config.transport_protocol = TransportProtocol(transport_value)
            source_config.youtube_quality = (
                quality_text if source_type == SourceType.YOUTUBE else "best"
            )
        else:
            from uuid import uuid4

            camera_id = str(uuid4())[:8]
            source_config = SourceConfig(
                transport_protocol=TransportProtocol(transport_value),
                reconnect_interval_sec=5.0,
                buffer_size=2,
                loop=False,
                youtube_quality=quality_text if source_type == SourceType.YOUTUBE else "best",
            )

        info = CameraInfo(
            id=camera_id,
            name=name,
            uri=uri,
            source_type=source_type,
            username=self._username_input.text().strip(),
            password=self._password_input.text().strip(),
            location=self._location_input.text().strip(),
            group_ids=self._selected_group_ids(),
            fps=self._fps_spin.value(),
            auto_reconnect=self._reconnect_check.isChecked(),
            source_config=source_config,
            enabled_features=self._get_selected_features(),
        )

        if self._mode == DialogMode.EDIT:
            self.camera_edited.emit(info)
        else:
            self.camera_added.emit(info)
        self.accept()

    def _selected_group_ids(self) -> list[str]:
        selected = self._group_combo.currentData()
        if selected:
            return [selected]
        return []
