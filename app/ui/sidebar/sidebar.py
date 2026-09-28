"""
Sidebar — tabbed panel with Cameras and Groups sections.

Architecture:
    CameraManager owns camera state (CameraRegistry).
    Sidebar only displays it.

    Custom segmented tab bar (Cameras / Groups) provides navigation.
    QStackedWidget switches between camera list and groups list.

    Each camera is a QListWidgetItem with a custom CameraItemWidget
    containing: checkbox, status indicator, name, source type, settings button.

    Checkboxes drive multi-selection for batch operations.
    Selection is explicit — never depends on insertion order.

Signals:
    cameras_checked_changed(list[str]) — emits checked camera IDs
    camera_selected(str)              — single click (highlight)
    camera_double_clicked(str)        — double click (open)
    add_camera_requested()            — "+" button
    edit_camera_requested(str)        — settings button clicked (camera_id)
    create_group_requested()          — "Create Group" button (placeholder)
    tab_changed(int)                  — tab index changed (0=C cameras, 1=Groups)
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QIcon, QPainter, QPainterPath, QPen, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QLabel,
    QPushButton,
    QFrame,
    QCheckBox,
    QSizePolicy,
    QAbstractItemView,
    QStackedLayout,
    QGraphicsDropShadowEffect,
    QMenu,
)

from app.models import CameraInfo, CameraStatus, SourceType
from app.core.groups.manager import GroupManager
from app.ui.sidebar.camera_context_menu import CameraContextMenu


# ── Status colors ────────────────────────────────────────────────────────────

_STATUS_COLORS: dict[CameraStatus, str] = {
    CameraStatus.ONLINE: "#22C55E",
    CameraStatus.OFFLINE: "#6B7280",
    CameraStatus.CONNECTING: "#3B82F6",
    CameraStatus.ERROR: "#EF4444",
    CameraStatus.BUFFERING: "#F59E0B",
    CameraStatus.DISCONNECTED: "#EF4444",
    CameraStatus.PAUSED: "#8B5CF6",
}

_STATUS_LABELS: dict[CameraStatus, str] = {
    CameraStatus.ONLINE: "Online",
    CameraStatus.OFFLINE: "Offline",
    CameraStatus.CONNECTING: "Connecting",
    CameraStatus.ERROR: "Error",
    CameraStatus.BUFFERING: "Buffering",
    CameraStatus.DISCONNECTED: "Disconnected",
    CameraStatus.PAUSED: "Paused",
}


def _source_type_short(st: SourceType) -> str:
    """Return short display name for source type."""
    _MAP = {
        SourceType.WEBCAM: "Webcam",
        SourceType.VIDEO_FILE: "Video",
        SourceType.RTSP: "RTSP",
        SourceType.HLS: "HLS",
        SourceType.YOUTUBE: "YouTube",
        SourceType.NETWORK_STREAM: "HTTP",
        SourceType.IP_CAMERA: "IP Cam",
        SourceType.ONVIF: "ONVIF",
    }
    return _MAP.get(st, st.value.upper()[:6])


# ── Segmented Tab Bar ────────────────────────────────────────────────────────

_TAB_HEIGHT = 32
_TAB_RADIUS = 6
_TAB_BORDER = "#3B4252"
_TAB_ACTIVE_BG = "#4F8EF7"
_TAB_ACTIVE_TEXT = "#FFFFFF"
_TAB_INACTIVE_BG = "#2A2F3C"
_TAB_INACTIVE_TEXT = "#BFC7D5"
_TAB_HOVER_BG = "#353A4A"
_TAB_HOVER_TEXT = "#FFFFFF"
_TAB_PRESSED_BG = "#3A7AE6"


class SegmentedTabBar(QWidget):
    """Custom segmented tab bar with dark industrial styling.

    Renders rounded pill-shaped tabs with an active indicator.
    No dependency on QTabBar — fully custom-painted for theme control.
    """

    tab_changed = Signal(int)  # emitted when user clicks a different tab

    def __init__(self, labels: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._labels = labels
        self._active_index = 0
        self._hover_index = -1
        self._pressed_index = -1
        self.setFixedHeight(_TAB_HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def active_index(self) -> int:
        return self._active_index

    def set_active_index(self, index: int) -> None:
        if 0 <= index < len(self._labels) and index != self._active_index:
            self._active_index = index
            self.update()
            self.tab_changed.emit(index)

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        count = len(self._labels)
        if count == 0:
            return

        tab_width = (w - 8) // count
        x_offset = 4

        for i, label in enumerate(self._labels):
            rect_x = x_offset + i * tab_width + 2
            rect_y = 4
            rect_w = tab_width - 4
            rect_h = h - 8
            is_active = i == self._active_index
            is_pressed = i == self._pressed_index
            is_hover = i == self._hover_index and not is_active

            path = QPainterPath()
            path.addRoundedRect(float(rect_x), float(rect_y), float(rect_w), float(rect_h), _TAB_RADIUS, _TAB_RADIUS)

            if is_active:
                painter.setBrush(QColor(_TAB_ACTIVE_BG))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPath(path)
                painter.setPen(QColor(_TAB_ACTIVE_TEXT))
                font = painter.font()
                font.setPixelSize(11)
                font.setWeight(QFont.Weight.DemiBold)
                painter.setFont(font)
            elif is_pressed:
                painter.setBrush(QColor(_TAB_PRESSED_BG))
                painter.setPen(QPen(QColor(_TAB_BORDER), 1))
                painter.drawPath(path)
                painter.setPen(QColor(_TAB_HOVER_TEXT))
                font = painter.font()
                font.setPixelSize(11)
                font.setWeight(QFont.Weight.Normal)
                painter.setFont(font)
            elif is_hover:
                painter.setBrush(QColor(_TAB_HOVER_BG))
                painter.setPen(QPen(QColor(_TAB_BORDER), 1))
                painter.drawPath(path)
                painter.setPen(QColor(_TAB_HOVER_TEXT))
                font = painter.font()
                font.setPixelSize(11)
                font.setWeight(QFont.Weight.Normal)
                painter.setFont(font)
            else:
                painter.setBrush(QColor(_TAB_INACTIVE_BG))
                painter.setPen(QPen(QColor(_TAB_BORDER), 1))
                painter.drawPath(path)
                painter.setPen(QColor(_TAB_INACTIVE_TEXT))
                font = painter.font()
                font.setPixelSize(11)
                font.setWeight(QFont.Weight.Normal)
                painter.setFont(font)

            painter.drawText(rect_x, rect_y, rect_w, rect_h, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(0, _TAB_HEIGHT)

    # ── Mouse events ──────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        idx = self._index_at(event.position().x())
        if idx != self._hover_index:
            self._hover_index = idx
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover_index = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        idx = self._index_at(event.position().x())
        if idx >= 0:
            self._pressed_index = idx
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        idx = self._index_at(event.position().x())
        if idx >= 0 and idx == self._pressed_index:
            self.set_active_index(idx)
        self._pressed_index = -1
        self.update()

    def _index_at(self, x: float) -> int:
        w = self.width()
        count = len(self._labels)
        if count == 0:
            return -1
        tab_width = (w - 8) // count
        for i in range(count):
            rect_x = 4 + i * tab_width + 2
            rect_w = tab_width - 4
            if rect_x <= x <= rect_x + rect_w:
                return i
        return -1


# ── Camera item widget ───────────────────────────────────────────────────────

class CameraItemWidget(QWidget):
    """Custom widget displayed inside each QListWidgetItem.

    Layout:
        [checkbox] [●] Camera Name
                    SourceType • Status
    """

    def __init__(self, info: CameraInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._info = info
        self._status = CameraStatus.OFFLINE
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(6)

        # Checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setFixedSize(16, 16)
        self._checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checkbox.setStyleSheet(
            "QCheckBox::indicator { width: 15px; height: 15px; border-radius: 3px; "
            "border: 1px solid #4B5060; background: #1A1D27; } "
            "QCheckBox::indicator:checked { background: #3B82F6; border-color: #3B82F6; } "
            "QCheckBox::indicator:hover { border-color: #3B82F6; }"
        )
        root.addWidget(self._checkbox, 0, Qt.AlignmentFlag.AlignTop)

        # Status indicator dot
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet(
            "background-color: #6B7280; border-radius: 4px; margin-top: 5px;"
        )
        root.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignTop)

        # Text column (stretches to fill available space)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)

        self._name_label = QLabel(self._info.name)
        self._name_label.setStyleSheet(
            "color: #E2E8F0; font-size: 12px; font-weight: 500; background: transparent;"
        )
        self._name_label.setWordWrap(False)
        self._name_label.setMinimumWidth(0)
        text_col.addWidget(self._name_label)

        detail_text = "%s \u2022 %s" % (
            _source_type_short(self._info.source_type),
            _STATUS_LABELS.get(self._status, "Unknown"),
        )
        self._detail_label = QLabel(detail_text)
        self._detail_label.setStyleSheet(
            "color: #8892A4; font-size: 10px; background: transparent;"
        )
        text_col.addWidget(self._detail_label)

        root.addLayout(text_col, 1)

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def camera_id(self) -> str:
        return self._info.id

    @property
    def checkbox(self) -> QCheckBox:
        return self._checkbox

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._checkbox.setChecked(checked)

    def set_status(self, status: CameraStatus) -> None:
        self._status = status
        color = _STATUS_COLORS.get(status, "#6B7280")
        self._dot.setStyleSheet(
            "background-color: %s; border-radius: 4px; margin-top: 5px;" % color
        )
        detail_text = "%s \u2022 %s" % (
            _source_type_short(self._info.source_type),
            _STATUS_LABELS.get(status, "Unknown"),
        )
        self._detail_label.setText(detail_text)

    def update_info(self, info: CameraInfo) -> None:
        self._info = info
        self._name_label.setText(info.name)
        detail_text = "%s \u2022 %s" % (
            _source_type_short(info.source_type),
            _STATUS_LABELS.get(self._status, "Unknown"),
        )
        self._detail_label.setText(detail_text)


# ── Group item widget ──────────────────────────────────────────────────────

_GROUP_ICONS = {
    "camera": "\U0001F4F7",
    "inbox": "\U0001F4E5",
    "building": "\U0001F3E2",
    "floor": "\U0001F6AA",
    "site": "\U0001F3D7",
    "star": "\u2B50",
}


class GroupItemWidget(QWidget):
    """Custom widget displayed inside each group QListWidgetItem.

    Layout:
        [icon] Group Name                   [count]
               Description
    """

    def __init__(self, group_data: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._group_data = group_data
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        icon_key = self._group_data.get("icon", "inbox")
        icon_char = _GROUP_ICONS.get(icon_key, "\U0001F4C1")

        self._icon_label = QLabel(icon_char)
        self._icon_label.setFixedSize(24, 24)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            "color: #8892A4; font-size: 14px; background: transparent;"
        )
        root.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)

        name = self._group_data.get("name", "Unnamed")
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(
            "color: #E2E8F0; font-size: 12px; font-weight: 500; background: transparent;"
        )
        self._name_label.setWordWrap(False)
        text_col.addWidget(self._name_label)

        count = self._group_data.get("camera_count", 0)
        self._count_label = QLabel("%d camera%s" % (count, "s" if count != 1 else ""))
        self._count_label.setStyleSheet(
            "color: #8892A4; font-size: 10px; background: transparent;"
        )
        text_col.addWidget(self._count_label)

        root.addLayout(text_col, 1)

    def update_data(self, group_data: dict) -> None:
        self._group_data = group_data
        self._name_label.setText(group_data.get("name", "Unnamed"))
        count = group_data.get("camera_count", 0)
        self._count_label.setText("%d camera%s" % (count, "s" if count != 1 else ""))


# ── Sidebar ──────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    """Left sidebar with segmented tabs (Cameras / Groups).

    CameraManager owns camera state. Sidebar only displays it.
    Checkbox selection drives batch operations (remove, record, etc).

    Tab switching only affects visible content — no camera state is altered.
    """

    cameras_checked_changed = Signal(list)  # list[str] — checked camera IDs
    camera_selected = Signal(str)           # camera_id — single click highlight
    camera_double_clicked = Signal(str)     # camera_id — double click open
    add_camera_requested = Signal()
    edit_camera_requested = Signal(str)     # camera_id — settings button clicked
    create_group_requested = Signal()
    edit_group_requested = Signal(str)      # group_id
    delete_group_requested = Signal(str)    # group_id
    group_selected = Signal(str)            # group_id — filter cameras by group
    hide_filter_requested = Signal()        # clear active filter and show all cameras
    tab_changed = Signal(int)              # tab index (0=C cameras, 1=Groups)
    camera_open_requested = Signal(list)    # camera_ids — reserved for future
    camera_remove_requested = Signal(list)  # camera_ids — remove from context menu
    camera_clear_selection_requested = Signal()
    camera_assign_group_requested = Signal(list, str)  # (camera_ids, group_id)
    camera_feature_toggled = Signal(list, str, bool)  # (camera_ids, feature_key, enabled)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(280)
        self.setMinimumHeight(200)

        self._camera_items: dict[str, CameraItemWidget] = {}
        self._list_items: dict[str, QListWidgetItem] = {}
        self._group_items: dict[str, QListWidgetItem] = {}
        self._group_widgets: dict[str, GroupItemWidget] = {}
        self._active_group_filter: Optional[str] = None
        self._all_cameras_shown: bool = True
        self._filter_allowed_ids: Optional[set[str]] = None
        self._context_menu = CameraContextMenu(self)
        self._setup_context_menu()

        self._build_ui()

    def set_group_manager(self, manager: GroupManager) -> None:
        """Set the GroupManager for the context menu's Assign Group submenu."""
        self._context_menu.set_group_manager(manager)

    def set_camera_repo(self, repo) -> None:
        """Set the camera repository for the context menu's Features submenu."""
        self._context_menu.set_camera_repo(repo)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Segmented Tab Bar ──────────────────────────────────
        self._tab_bar = SegmentedTabBar(["Cameras", "Groups"])
        self._tab_bar.tab_changed.connect(self._on_tab_changed)
        root.addWidget(self._tab_bar)

        # ── Stacked content (cameras page / groups page) ───────
        self._stack = QStackedLayout()
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._cameras_page = self._build_cameras_page()
        self._groups_page = self._build_groups_page()

        self._stack.addWidget(self._cameras_page)
        self._stack.addWidget(self._groups_page)
        self._stack.setCurrentIndex(0)

        root.addLayout(self._stack, 1)

        # ── Bottom bar (cameras only — shown/hidden by tab) ────
        self._bottom_frame = QFrame()
        self._bottom_frame.setStyleSheet(
            "QFrame { background: #1A1D27; border-top: 1px solid #2E3140; }"
        )
        bottom_layout = QHBoxLayout(self._bottom_frame)
        bottom_layout.setContentsMargins(12, 6, 12, 6)

        self._checked_label = QLabel("0 selected")
        self._checked_label.setStyleSheet(
            "color: #3B82F6; font-size: 11px; font-weight: 500; background: transparent;"
        )
        bottom_layout.addWidget(self._checked_label)
        bottom_layout.addStretch()

        self._online_label = QLabel("0 online")
        self._online_label.setStyleSheet(
            "color: #22C55E; font-size: 11px; background: transparent;"
        )
        bottom_layout.addWidget(self._online_label)

        root.addWidget(self._bottom_frame)

    def _setup_context_menu(self) -> None:
        """Connect context menu signals to sidebar signals."""
        self._context_menu.open_requested.connect(self.camera_open_requested.emit)
        self._context_menu.settings_requested.connect(self.edit_camera_requested.emit)
        self._context_menu.assign_group_requested.connect(
            self.camera_assign_group_requested.emit
        )
        self._context_menu.feature_toggled.connect(
            self.camera_feature_toggled.emit
        )
        self._context_menu.remove_requested.connect(self.camera_remove_requested.emit)
        self._context_menu.clear_selection_requested.connect(
            self.camera_clear_selection_requested.emit
        )

    def _build_cameras_page(self) -> QWidget:
        """Build the Cameras tab content: filter indicator + search + add button + camera list."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Filter indicator (hidden by default)
        self._filter_frame = QFrame()
        self._filter_frame.setStyleSheet(
            "QFrame { background: #21242F; border-bottom: 1px solid #2E3140; }"
        )
        filter_layout = QHBoxLayout(self._filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)
        filter_layout.setSpacing(4)

        filter_label = QLabel("Showing:")
        filter_label.setStyleSheet(
            "color: #8892A4; font-size: 10px; background: transparent;"
        )
        filter_layout.addWidget(filter_label)

        self._filter_name_label = QLabel("")
        self._filter_name_label.setStyleSheet(
            "color: #3B82F6; font-size: 11px; font-weight: 500; background: transparent;"
        )
        filter_layout.addWidget(self._filter_name_label)

        filter_layout.addStretch()

        clear_filter_btn = QPushButton("\u2716")  # ✖
        clear_filter_btn.setObjectName("clearFilterButton")
        clear_filter_btn.setFixedSize(16, 16)
        clear_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_filter_btn.setToolTip("Clear Filter")
        clear_filter_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8892A4; "
            "font-size: 10px; }"
            "QPushButton:hover { color: #E2E8F0; }"
        )
        clear_filter_btn.clicked.connect(self._on_clear_filter_clicked)
        filter_layout.addWidget(clear_filter_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._filter_frame.setVisible(False)
        page_layout.addWidget(self._filter_frame)

        # Search + add button row
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(8, 6, 8, 6)
        search_layout.setSpacing(4)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search cameras...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        add_btn = QPushButton("+")
        add_btn.setObjectName("iconButton")
        add_btn.setFixedSize(24, 24)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add Camera")
        add_btn.clicked.connect(self.add_camera_requested.emit)
        search_layout.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignRight)

        page_layout.addWidget(search_frame)

        # Camera list
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSpacing(1)
        self._list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { padding: 0px; }"
            "QListWidget::item:selected { background: transparent; }"
            "QListWidget::item:hover { background: #21242F; }"
        )
        self._list.currentRowChanged.connect(self._on_row_clicked)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_camera_context_menu)
        page_layout.addWidget(self._list, 1)

        return page

    def _build_groups_page(self) -> QWidget:
        """Build the Groups tab content: search + group list + empty state."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Search + add button row
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(8, 6, 8, 6)
        search_layout.setSpacing(4)
        self._group_search_input = QLineEdit()
        self._group_search_input.setPlaceholderText("Search groups...")
        self._group_search_input.setClearButtonEnabled(True)
        self._group_search_input.textChanged.connect(self._on_group_search)
        search_layout.addWidget(self._group_search_input, 1)

        add_group_btn = QPushButton("+")
        add_group_btn.setObjectName("iconButton")
        add_group_btn.setFixedSize(24, 24)
        add_group_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_group_btn.setToolTip("Create Group")
        add_group_btn.clicked.connect(self.create_group_requested.emit)
        search_layout.addWidget(add_group_btn, 0, Qt.AlignmentFlag.AlignRight)

        page_layout.addWidget(search_frame)

        # Group list
        self._group_list = QListWidget()
        self._group_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._group_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._group_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._group_list.setSpacing(1)
        self._group_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { padding: 0px; }"
            "QListWidget::item:selected { background: transparent; }"
            "QListWidget::item:hover { background: #21242F; }"
        )
        #         # Left-click disabled — use right-click "Show" instead
        self._group_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._group_list.customContextMenuRequested.connect(self._on_group_context_menu)
        page_layout.addWidget(self._group_list, 1)

        # Empty state (hidden by default, shown when no groups exist)
        self._groups_empty = self._build_groups_empty_state()
        page_layout.addWidget(self._groups_empty)

        return page

    def _build_groups_empty_state(self) -> QWidget:
        """Build the empty-state widget shown when no groups exist."""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
        icon_label = QLabel("\u2630")  # ☰
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            "color: #4B5060; font-size: 32px; background: transparent;"
        )
        layout.addWidget(icon_label)

        # Title
        title = QLabel("No Groups")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #E2E8F0; font-size: 13px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(title)

        # Description
        desc = QLabel("Create your first camera group\nto organize cameras by location or type.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(
            "color: #8892A4; font-size: 11px; background: transparent;"
        )
        layout.addWidget(desc)

        layout.addSpacing(8)

        # Create Group button
        create_btn = QPushButton("+ Create Group")
        create_btn.setObjectName("accent")
        create_btn.setFixedWidth(160)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create_group_clicked)
        layout.addWidget(create_btn, 0, Qt.AlignmentFlag.AlignCenter)

        return widget

    # ── Tab switching ─────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        """Switch visible content. No camera state is affected."""
        self._stack.setCurrentIndex(index)
        self._bottom_frame.setVisible(index == 0)
        self.tab_changed.emit(index)

    def _on_create_group_clicked(self) -> None:
        """Placeholder handler for Create Group button."""
        self.create_group_requested.emit()

    def show_filter_indicator(self, group_name: str) -> None:
        """Show the filter indicator with the group name."""
        self._filter_name_label.setText(group_name)
        self._filter_frame.setVisible(True)

    def hide_filter_indicator(self) -> None:
        """Hide the filter indicator."""
        self._filter_frame.setVisible(False)
        self._filter_name_label.setText("")

    def _on_clear_filter_clicked(self) -> None:
        """Handle Clear Filter button click."""
        self.hide_filter_requested.emit()

    # ── Public API ────────────────────────────────────────────────────────

    def add_camera(self, info: CameraInfo) -> None:
        """Add a camera to the sidebar list."""
        if info.id in self._camera_items:
            return

        item_widget = CameraItemWidget(info)
        item_widget.checkbox.stateChanged.connect(self._on_checkbox_changed)

        list_item = QListWidgetItem()
        list_item.setSizeHint(QSize(0, 48))
        list_item.setData(Qt.ItemDataRole.UserRole, info.id)
        list_item.setFlags(
            list_item.flags()
            & ~Qt.ItemFlag.ItemIsSelectable
            & ~Qt.ItemFlag.ItemIsEditable
        )

        self._list.addItem(list_item)
        self._list.setItemWidget(list_item, item_widget)

        self._camera_items[info.id] = item_widget
        self._list_items[info.id] = list_item

        self._update_labels()

    def remove_camera(self, camera_id: str) -> None:
        """Remove a camera from the sidebar list."""
        widget = self._camera_items.pop(camera_id, None)
        list_item = self._list_items.pop(camera_id, None)

        if list_item is not None:
            row = self._list.row(list_item)
            if row >= 0:
                self._list.takeItem(row)

        self._update_labels()

    def set_camera_status(self, camera_id: str, status: CameraStatus) -> None:
        """Update the status display of a camera."""
        widget = self._camera_items.get(camera_id)
        if widget is not None:
            widget.set_status(status)

    def get_checked_ids(self) -> list[str]:
        """Return all currently checked camera IDs."""
        return [
            cam_id
            for cam_id, widget in self._camera_items.items()
            if widget.is_checked()
        ]

    def set_checked_ids(self, camera_ids: list[str]) -> None:
        """Set which cameras are checked."""
        for cam_id, widget in self._camera_items.items():
            widget.set_checked(cam_id in camera_ids)
        self._update_labels()

    def clear_checked(self) -> None:
        """Uncheck all cameras."""
        for widget in self._camera_items.values():
            widget.set_checked(False)
        self._update_labels()

    def select_all(self) -> None:
        """Check all cameras."""
        for widget in self._camera_items.values():
            widget.set_checked(True)
        self._update_labels()

    def deselect_all(self) -> None:
        """Uncheck all cameras (alias for clear_checked)."""
        self.clear_checked()

    def invert_selection(self) -> None:
        """Toggle all checkboxes."""
        for widget in self._camera_items.values():
            widget.set_checked(not widget.is_checked())
        self._update_labels()

    def camera_count(self) -> int:
        return len(self._camera_items)

    def checked_count(self) -> int:
        return len(self.get_checked_ids())

    def update_counts(self, total: int, online: int) -> None:
        """Update count labels from the centralized source of truth (CameraRegistry).

        Total and online values MUST come from CameraRegistry, never computed here.
        Only the checked count is local state.
        """
        checked = len(self.get_checked_ids())
        self._checked_label.setText(
            "%d selected" % checked if checked > 0 else ""
        )
        self._online_label.setText("%d online" % online)

    def clear(self) -> None:
        self._list.clear()
        self._camera_items.clear()
        self._list_items.clear()
        self._update_labels()

    # ── Search filtering ──────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        """Filter camera list by name, source type, or status.

        Respects active group filter — search only applies within filtered set.
        """
        text_lower = text.strip().lower()

        for cam_id, list_item in self._list_items.items():
            widget = self._camera_items.get(cam_id)
            if widget is None:
                continue

            # If group filter is active, camera must be in allowed set
            in_group = True
            if self._active_group_filter is not None and self._filter_allowed_ids is not None:
                in_group = cam_id in self._filter_allowed_ids

            if not text_lower:
                list_item.setHidden(not in_group)
                continue

            name_match = text_lower in widget._info.name.lower()
            type_match = text_lower in widget._info.source_type.value.lower()
            status_text = _STATUS_LABELS.get(widget._status, "").lower()
            status_match = text_lower in status_text
            location_match = text_lower in widget._info.location.lower()

            search_match = name_match or type_match or status_match or location_match
            list_item.setHidden(not (in_group and search_match))

    # ── Internal handlers ─────────────────────────────────────────────────

    def _on_checkbox_changed(self, state: int) -> None:
        """Handle any checkbox state change."""
        self._update_labels()
        self.cameras_checked_changed.emit(self.get_checked_ids())

    def _on_row_clicked(self, row: int) -> None:
        """Handle row click — emit camera_selected for highlighting."""
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        cam_id = item.data(Qt.ItemDataRole.UserRole)
        if cam_id:
            self.camera_selected.emit(cam_id)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Handle double click — emit camera_double_clicked."""
        cam_id = item.data(Qt.ItemDataRole.UserRole)
        if cam_id:
            self.camera_double_clicked.emit(cam_id)

    def _on_camera_context_menu(self, pos) -> None:
        """Handle right-click on camera list — show context menu."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        clicked_id = item.data(Qt.ItemDataRole.UserRole)
        if not clicked_id:
            return

        checked_ids = self.get_checked_ids()
        self._context_menu.build(clicked_id, checked_ids)
        self._context_menu.exec(self._list.mapToGlobal(pos))

    def _update_labels(self) -> None:
        """Update the checked count label only.

        Total and online counts are provided externally via update_counts()
        from the centralized CameraRegistry source of truth.
        """
        checked = len(self.get_checked_ids())
        self._checked_label.setText(
            "%d selected" % checked if checked > 0 else ""
        )

    # ── Group management ─────────────────────────────────────────────────

    def set_groups(self, groups: list[dict]) -> None:
        """Rebuild the groups list from GroupManager data.

        Each dict: {id, name, camera_count, is_builtin, icon, color, is_favorite}
        """
        self._group_list.clear()
        self._group_items.clear()
        self._group_widgets.clear()

        for g in groups:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 48))
            item.setData(Qt.ItemDataRole.UserRole, g["id"])
            widget = GroupItemWidget(g)
            self._group_list.addItem(item)
            self._group_list.setItemWidget(item, widget)
            self._group_items[g["id"]] = item
            self._group_widgets[g["id"]] = widget

        has_groups = len(groups) > 0
        self._group_list.setVisible(has_groups)
        self._groups_empty.setVisible(not has_groups)

    def set_group_filter(self, group_id: Optional[str]) -> None:
        """Set the active group filter. None means show all cameras."""
        self._active_group_filter = group_id
        self._all_cameras_shown = group_id is None
        self._apply_group_filter()

    def get_active_group_filter(self) -> Optional[str]:
        """Return the currently active group filter ID, or None for all."""
        return self._active_group_filter

    def _apply_group_filter(self) -> None:
        """Show/hide camera list items based on the active group filter.

        Called by MainWindow after receiving group_selected signal.
        The actual filter logic lives in GroupManager — Sidebar just
        shows/hides items based on the allowed camera_ids set.
        """
        if self._active_group_filter is None:
            for cam_id, list_item in self._list_items.items():
                list_item.setHidden(False)
            return

        if self._filter_allowed_ids is not None:
            for cam_id, list_item in self._list_items.items():
                list_item.setHidden(cam_id not in self._filter_allowed_ids)

    def set_filter_allowed_ids(self, allowed_ids: Optional[set[str]]) -> None:
        """Set which camera IDs are allowed by the current filter.

        Call before set_group_filter() to apply a custom filter set.
        If None, all cameras are shown (overriding group filter).
        """
        if allowed_ids is None:
            self._filter_allowed_ids = None
        else:
            self._filter_allowed_ids = allowed_ids
        self._apply_group_filter()

    def _on_group_row_clicked(self, row: int) -> None:
        """Handle group row click — emit group_selected for filtering."""
        if row < 0:
            return
        item = self._group_list.item(row)
        if item is None:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        if group_id:
            self.group_selected.emit(group_id)

    def _on_group_context_menu(self, pos) -> None:
        """Handle right-click context menu on group list.

        System groups (All Cameras, Ungrouped): Show only "Show" action.
        User groups: Show "Show", "Edit Group", "Delete Group".
        """
        item = self._group_list.itemAt(pos)
        if item is None:
            return
        group_id = item.data(Qt.ItemDataRole.UserRole)
        if not group_id:
            return
        widget = self._group_widgets.get(group_id)
        if widget is None:
            return

        is_builtin = widget._group_data.get("is_builtin", False)

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1A1D27; border: 1px solid #2E3140; border-radius: 6px; padding: 4px; }"
            "QMenu::item { padding: 6px 16px; color: #E2E8F0; border-radius: 4px; }"
            "QMenu::item:selected { background: #3B82F6; color: white; }"
            "QMenu::separator { height: 1px; background: #2E3140; margin: 4px 8px; }"
        )

        show_action = menu.addAction("Show")

        if not is_builtin:
            menu.addSeparator()
            edit_action = menu.addAction("Edit Group")
            delete_action = menu.addAction("Delete Group")

        action = menu.exec(self._group_list.mapToGlobal(pos))
        if action == show_action:
            self.group_selected.emit(group_id)
        elif not is_builtin and action == edit_action:
            self.edit_group_requested.emit(group_id)
        elif not is_builtin and action == delete_action:
            self.delete_group_requested.emit(group_id)

    def _on_group_search(self, text: str) -> None:
        """Filter group list by name."""
        text_lower = text.strip().lower()
        for group_id, list_item in self._group_items.items():
            if not text_lower:
                list_item.setHidden(False)
                continue
            widget = self._group_widgets.get(group_id)
            if widget is None:
                continue
            name_match = text_lower in widget._group_data.get("name", "").lower()
            list_item.setHidden(not name_match)
