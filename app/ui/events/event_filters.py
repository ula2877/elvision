from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QPushButton,
    QLabel,
    QDialog,
    QFrame,
)

from app.core.events.models import (
    EventFilter,
    EVENT_TYPES_ALL,
    EVENT_TYPE_LABELS,
    EVENT_STATUS_ALL,
)


_CONTROL_HEIGHT = 28


class AdvancedFilterDialog(QDialog):
    def __init__(
        self,
        group_names: list[str],
        current: EventFilter,
        parent=None,
        delete_all_callback=None,
    ) -> None:
        super().__init__(parent)
        self._result = EventFilter()
        self._delete_all_callback = delete_all_callback
        self.setWindowTitle("Advanced Filters")
        self.setFixedSize(320, 290)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        date_label = QLabel("Date Range")
        date_label.setStyleSheet("font-weight: 600; color: #E2E8F0;")
        layout.addWidget(date_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("From:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setSpecialValueText("Any")
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        if current.date_from:
            qd = QDate.fromString(current.date_from, "yyyy-MM-dd")
            if qd.isValid():
                self._date_from.setDate(qd)
        row.addWidget(self._date_from)

        row.addWidget(QLabel("To:"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setSpecialValueText("Any")
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        if current.date_to:
            qd = QDate.fromString(current.date_to, "yyyy-MM-dd")
            if qd.isValid():
                self._date_to.setDate(qd)
        row.addWidget(self._date_to)
        layout.addLayout(row)

        group_label = QLabel("Group")
        group_label.setStyleSheet("font-weight: 600; color: #E2E8F0;")
        layout.addWidget(group_label)

        self._group_combo = QComboBox()
        self._group_combo.addItem("All Groups", None)
        for gn in group_names:
            self._group_combo.addItem(gn, gn)
        if current.group_name:
            idx = self._group_combo.findData(current.group_name)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)
        layout.addWidget(self._group_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #334155;")
        layout.addWidget(sep)

        if self._delete_all_callback:
            del_all_btn = QPushButton("Delete All Events...")
            del_all_btn.setStyleSheet(
                "QPushButton { color: #EF4444; text-align: left; padding: 6px 8px; "
                "background: transparent; border: 1px solid #334155; border-radius: 4px; "
                "font-size: 12px; } "
                "QPushButton:hover { background-color: #1E293B; border-color: #EF4444; }"
            )
            del_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_all_btn.clicked.connect(self._on_delete_all)
            layout.addWidget(del_all_btn)

        layout.addStretch()

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn)

        layout.addLayout(btn_row)

    def _on_delete_all(self) -> None:
        if self._delete_all_callback:
            self._delete_all_callback()

    def _clear(self) -> None:
        self._date_from.setDate(self._date_from.minimumDate())
        self._date_to.setDate(self._date_to.maximumDate())
        self._group_combo.setCurrentIndex(0)

    def _apply(self) -> None:
        self._result = EventFilter()

        dt = self._date_from.date()
        if dt != self._date_from.minimumDate():
            self._result.date_from = dt.toString("yyyy-MM-dd")

        dt = self._date_to.date()
        if dt != self._date_to.maximumDate():
            self._result.date_to = dt.toString("yyyy-MM-dd")

        self._result.group_name = self._group_combo.currentData()
        self.accept()

    def get_filter(self) -> EventFilter:
        return self._result


class EventFilters(QWidget):
    filter_changed = Signal()
    delete_all_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._camera_ids: list[str] = []
        self._group_names: list[str] = []
        self._advanced_filter = EventFilter()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(160)
        self._search.setFixedHeight(_CONTROL_HEIGHT)
        self._search.textChanged.connect(self._on_changed)
        layout.addWidget(self._search)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras", None)
        self._camera_combo.setFixedHeight(_CONTROL_HEIGHT)
        self._camera_combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._camera_combo)

        self._type_combo = QComboBox()
        self._type_combo.addItem("All Events", None)
        for et in EVENT_TYPES_ALL:
            self._type_combo.addItem(EVENT_TYPE_LABELS.get(et, et), et)
        self._type_combo.setFixedHeight(_CONTROL_HEIGHT)
        self._type_combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._type_combo)

        self._status_combo = QComboBox()
        self._status_combo.addItem("All Status", None)
        for st in EVENT_STATUS_ALL:
            self._status_combo.addItem(st.capitalize(), st)
        self._status_combo.setFixedHeight(_CONTROL_HEIGHT)
        self._status_combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._status_combo)

        self._advanced_btn = QPushButton("Advanced \u25be")
        self._advanced_btn.setFixedHeight(_CONTROL_HEIGHT)
        self._advanced_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_btn.clicked.connect(self._show_advanced)
        layout.addWidget(self._advanced_btn)

        layout.addStretch()

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            EventFilters QLineEdit,
            EventFilters QComboBox,
            EventFilters QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 4px;
                color: #E2E8F0;
                padding: 4px 8px;
                font-size: 12px;
            }
            EventFilters QLineEdit:focus,
            EventFilters QComboBox:focus {
                border-color: #3B82F6;
            }
            EventFilters QComboBox:hover,
            EventFilters QPushButton:hover {
                border-color: #3B82F6;
            }
            EventFilters QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            EventFilters QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #64748B;
                margin-right: 4px;
            }
            EventFilters QComboBox QAbstractItemView {
                background-color: #1E293B;
                color: #E2E8F0;
                selection-background-color: #1D4ED8;
                border: 1px solid #334155;
                outline: none;
            }
            EventFilters QPushButton {
                text-align: left;
                padding-right: 8px;
            }
            EventFilters QPushButton:pressed {
                background-color: #1D4ED8;
            }
        """)

    def set_camera_ids(self, ids: list[str]) -> None:
        self._camera_ids = ids
        current = self._camera_combo.currentData()
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_combo.addItem("All Cameras", None)
        for cid in ids:
            self._camera_combo.addItem(cid, cid)
        idx = self._camera_combo.findData(current)
        if idx >= 0:
            self._camera_combo.setCurrentIndex(idx)
        self._camera_combo.blockSignals(False)

    def set_group_names(self, names: list[str]) -> None:
        self._group_names = names

    def to_filter(self) -> EventFilter:
        f = EventFilter()
        f.search = self._search.text().strip()
        f.camera_id = self._camera_combo.currentData()
        f.event_type = self._type_combo.currentData()
        f.status = self._status_combo.currentData()
        f.date_from = self._advanced_filter.date_from
        f.date_to = self._advanced_filter.date_to
        f.group_name = self._advanced_filter.group_name
        return f

    def _on_changed(self) -> None:
        self.filter_changed.emit()

    def _show_advanced(self) -> None:
        dlg = AdvancedFilterDialog(
            self._group_names, self._advanced_filter, self,
            delete_all_callback=self.delete_all_requested.emit,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._advanced_filter = dlg.get_filter()
            has_advanced = bool(
                self._advanced_filter.date_from
                or self._advanced_filter.date_to
                or self._advanced_filter.group_name
            )
            self._advanced_btn.setText("Advanced \u25cf" if has_advanced else "Advanced \u25be")
            self.filter_changed.emit()
