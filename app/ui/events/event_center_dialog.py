from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QHeaderView,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QMenu,
    QLabel,
    QWidget,
    QApplication,
    QComboBox,
)

from app.core.events.manager import EventManager
from app.core.events.models import (
    EventRecord,
    EVENT_STATUS_ACKNOWLEDGED,
    EVENT_STATUS_RESOLVED,
    EVENT_STATUS_DISMISSED,
)
from app.ui.events.event_model import (
    EventTableModel,
    EventSortProxy,
    COL_SNAPSHOT,
    COL_TIME,
    COL_CAMERA,
    COL_EVENT,
    COL_CONFIDENCE,
    COL_STATUS,
    COL_GROUP,
    COL_NOTES,
)
from app.ui.events.event_filters import EventFilters
from app.ui.events.event_detail import EventDetailDialog
from app.ui.events.exporter import EventExporter


_PAGE_SIZES = [25, 50, 100, 250, 500]
_DEFAULT_PAGE_SIZE = 100


class EventCenterDialog(QDialog):
    def __init__(self, manager: EventManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._exporter = EventExporter()

        self._current_page = 1
        self._page_size = _DEFAULT_PAGE_SIZE
        self._total_count = 0
        self._total_pages = 1

        self.setWindowTitle("Event Center")
        self.setMinimumSize(900, 600)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._build_ui()
        self._connect_signals()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar (global actions only) ─────────────────
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background-color: #0F172A;")
        tool_row = QHBoxLayout(toolbar_widget)
        tool_row.setContentsMargins(0, 0, 0, 0)
        tool_row.setSpacing(0)

        self._filters = EventFilters()
        tool_row.addWidget(self._filters, 1)

        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 4, 8, 4)
        action_bar.setSpacing(8)

        self._refresh_btn = QPushButton("\u21bb  Refresh")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._refresh)
        action_bar.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("Export  \u25be")
        self._export_btn.setFixedHeight(28)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.clicked.connect(self._show_export_menu)
        action_bar.addWidget(self._export_btn)

        tool_row.addLayout(action_bar)
        root.addWidget(toolbar_widget)

        # Toolbar action button styling
        self._toolbar_style = (
            "QPushButton {"
            "  background-color: #1E293B;"
            "  border: 1px solid #334155;"
            "  border-radius: 4px;"
            "  color: #E2E8F0;"
            "  padding: 4px 12px;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  border-color: #3B82F6;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #1D4ED8;"
            "}"
        )
        self._refresh_btn.setStyleSheet(self._toolbar_style)
        self._export_btn.setStyleSheet(self._toolbar_style)

        # ── Table ─────────────────────────────────────────
        self._model = EventTableModel(self)
        self._proxy = EventSortProxy(self)
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setWordWrap(True)
        self._table.verticalHeader().hide()
        self._table.verticalHeader().setDefaultSectionSize(40)
        self._table.setSortingEnabled(True)

        hdr = self._table.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setSectionsClickable(True)

        hdr.setSectionResizeMode(COL_SNAPSHOT, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_SNAPSHOT, 65)

        hdr.setSectionResizeMode(COL_TIME, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_TIME, 105)

        hdr.setSectionResizeMode(COL_CAMERA, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_CAMERA, 200)

        hdr.setSectionResizeMode(COL_EVENT, QHeaderView.ResizeMode.Stretch)

        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_STATUS, 140)

        self._table.setColumnHidden(COL_GROUP, True)
        self._table.setColumnHidden(COL_CONFIDENCE, True)
        self._table.setColumnHidden(COL_NOTES, True)

        self._table.setStyleSheet(
            "QTableView { background-color: #0F172A; alternate-background-color: #1E293B; "
            "color: #E2E8F0; border: none; font-size: 12px; } "
            "QTableView::item { padding: 4px 8px; border: none; "
            "border-right: 1px solid #32384A; } "
            "QTableView::item:selected { background-color: #1D4ED8; "
            "border-right: 1px solid #32384A; } "
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; "
            "padding: 6px 8px; border: none; border-bottom: 1px solid #334155; "
            "border-right: 1px solid #32384A; "
            "font-weight: 600; font-size: 11px; } "
            "QHeaderView::section:last { border-right: none; }"
        )

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        root.addWidget(self._table, 1)

        # ── Pagination Bar ────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 4, 8, 4)
        footer.setSpacing(6)

        self._showing_label = QLabel()
        self._showing_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        footer.addWidget(self._showing_label)

        self._selected_label = QLabel()
        self._selected_label.setStyleSheet("color: #3B82F6; font-size: 11px;")
        footer.addWidget(self._selected_label)

        footer.addStretch()

        self._first_btn = QPushButton("<<")
        self._first_btn.setFixedHeight(24)
        self._first_btn.setFixedWidth(36)
        self._first_btn.setToolTip("First Page")
        self._first_btn.clicked.connect(self._go_to_first_page)
        footer.addWidget(self._first_btn)

        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedHeight(24)
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.setToolTip("Previous Page")
        self._prev_btn.clicked.connect(self._go_to_prev_page)
        footer.addWidget(self._prev_btn)

        self._page_label = QLabel("Page 1 / 1")
        self._page_label.setStyleSheet("color: #E2E8F0; font-size: 11px; padding: 0 6px;")
        footer.addWidget(self._page_label)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedHeight(24)
        self._next_btn.setFixedWidth(32)
        self._next_btn.setToolTip("Next Page")
        self._next_btn.clicked.connect(self._go_to_next_page)
        footer.addWidget(self._next_btn)

        self._last_btn = QPushButton(">>")
        self._last_btn.setFixedHeight(24)
        self._last_btn.setFixedWidth(36)
        self._last_btn.setToolTip("Last Page")
        self._last_btn.clicked.connect(self._go_to_last_page)
        footer.addWidget(self._last_btn)

        footer.addSpacing(12)

        rows_label = QLabel("Rows:")
        rows_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        footer.addWidget(rows_label)

        self._page_size_combo = QComboBox()
        self._page_size_combo.setFixedWidth(64)
        self._page_size_combo.setFixedHeight(24)
        for ps in _PAGE_SIZES:
            self._page_size_combo.addItem(str(ps), ps)
        idx = self._page_size_combo.findData(_DEFAULT_PAGE_SIZE)
        if idx >= 0:
            self._page_size_combo.setCurrentIndex(idx)
        self._page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        footer.addWidget(self._page_size_combo)

        root.addLayout(footer)

        self._apply_pagination_style()

    def _connect_signals(self) -> None:
        self._filters.filter_changed.connect(self._on_filter_changed)
        self._filters.delete_all_requested.connect(self._delete_all)
        self._table.doubleClicked.connect(self._open_selected_detail)
        self._manager.event_created.connect(self._on_new_event)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._table.selectionModel().hasSelection():
                self._table.clearSelection()
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Delete:
            if self._table.hasFocus() and self._table.selectionModel().hasSelection():
                self._delete_selected()
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_new_event(self, event: EventRecord) -> None:
        self._refresh()

    def _on_filter_changed(self) -> None:
        self._current_page = 1
        self._refresh()

    def _refresh(self) -> None:
        filter_ = self._filters.to_filter()
        self._total_count = self._manager.count(filter_)
        self._total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._current_page > self._total_pages:
            self._current_page = self._total_pages

        offset = (self._current_page - 1) * self._page_size
        events = self._manager.query(filter_, limit=self._page_size, offset=offset)
        self._model.set_events(events)

        start = offset + 1 if self._total_count > 0 else 0
        end = min(offset + self._page_size, self._total_count)
        self._showing_label.setText(
            f"Showing {start}\u2013{end} of {self._total_count} events"
            if self._total_count > 0 else "Showing 0 events"
        )
        self._update_pagination_controls()

        cameras = self._manager.distinct_cameras()
        self._filters.set_camera_ids(cameras)

        groups = self._manager.distinct_groups()
        self._filters.set_group_names(groups)

    def _update_pagination_controls(self) -> None:
        self._page_label.setText(f"Page {self._current_page} / {self._total_pages}")
        self._first_btn.setEnabled(self._current_page > 1)
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(self._current_page < self._total_pages)
        self._last_btn.setEnabled(self._current_page < self._total_pages)

    def _go_to_first_page(self) -> None:
        self._current_page = 1
        self._refresh()

    def _go_to_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._refresh()

    def _go_to_next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._refresh()

    def _go_to_last_page(self) -> None:
        self._current_page = self._total_pages
        self._refresh()

    def _on_page_size_changed(self) -> None:
        self._page_size = self._page_size_combo.currentData()
        self._current_page = 1
        self._refresh()

    def _apply_pagination_style(self) -> None:
        btn_style = (
            "QPushButton {"
            "  background-color: #1E293B;"
            "  border: 1px solid #334155;"
            "  border-radius: 3px;"
            "  color: #E2E8F0;"
            "  font-size: 11px;"
            "  padding: 0;"
            "}"
            "QPushButton:hover {"
            "  border-color: #3B82F6;"
            "}"
            "QPushButton:disabled {"
            "  color: #475569;"
            "  border-color: #1E293B;"
            "}"
        )
        self._first_btn.setStyleSheet(btn_style)
        self._prev_btn.setStyleSheet(btn_style)
        self._next_btn.setStyleSheet(btn_style)
        self._last_btn.setStyleSheet(btn_style)

        combo_style = (
            "QComboBox {"
            "  background-color: #1E293B;"
            "  border: 1px solid #334155;"
            "  border-radius: 3px;"
            "  color: #E2E8F0;"
            "  font-size: 11px;"
            "  padding: 2px 4px;"
            "}"
            "QComboBox::drop-down {"
            "  border: none;"
            "  width: 16px;"
            "}"
            "QComboBox::down-arrow {"
            "  image: none;"
            "  border-left: 3px solid transparent;"
            "  border-right: 3px solid transparent;"
            "  border-top: 4px solid #64748B;"
            "}"
            "QComboBox:hover {"
            "  border-color: #3B82F6;"
            "}"
            "QComboBox QAbstractItemView {"
            "  background-color: #1E293B;"
            "  color: #E2E8F0;"
            "  selection-background-color: #1D4ED8;"
            "  border: 1px solid #334155;"
            "}"
        )
        self._page_size_combo.setStyleSheet(combo_style)

    def _on_selection_changed(self) -> None:
        count = len(self._table.selectionModel().selectedRows())
        if count > 0:
            self._selected_label.setText(f"Selected: {count} event{'s' if count != 1 else ''}")
        else:
            self._selected_label.setText("")

    def _map_to_source(self, proxy_index):
        return self._proxy.mapToSource(proxy_index)

    def _open_selected_detail(self) -> None:
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        src_idx = self._map_to_source(idx)
        ev = self._model.event_at(src_idx.row())
        if ev is None:
            return
        dialog = EventDetailDialog(ev, self._manager, self)
        dialog.exec()
        self._refresh()

    def _show_context_menu(self, pos) -> None:
        has_selection = self._table.selectionModel().hasSelection()
        if not has_selection:
            return

        menu = QMenu(self._table)

        menu.addAction("Open Detail...", self._open_selected_detail)
        menu.addAction("Open Snapshot", self._open_snapshot_selected)
        menu.addSeparator()

        status_menu = menu.addMenu("Status")
        status_menu.addAction("New", lambda: self._update_selected_status("new"))
        status_menu.addAction(
            "Acknowledged", lambda: self._update_selected_status(EVENT_STATUS_ACKNOWLEDGED)
        )
        status_menu.addAction(
            "Resolved", lambda: self._update_selected_status(EVENT_STATUS_RESOLVED)
        )
        status_menu.addAction(
            "Dismissed", lambda: self._update_selected_status(EVENT_STATUS_DISMISSED)
        )

        menu.addSeparator()
        menu.addAction("Delete Event", self._delete_selected)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _open_snapshot_selected(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        for ev in self._model._events:
            if ev.id in ids and ev.snapshot_path:
                path = Path(ev.snapshot_path)
                if path.exists():
                    subprocess.Popen(["start", "", str(path)], shell=True)

    def _update_selected_status(self, status: str) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        for ev_id in ids:
            self._manager.update_status(ev_id, status)
        self._refresh()

    def _show_export_menu(self) -> None:
        has_selection = self._table.selectionModel().hasSelection()
        menu = QMenu(self._export_btn)
        menu.addAction("Export Current Filter", self._export_current_filter)
        menu.addAction("Export All", self._export_all)
        if has_selection:
            menu.addSeparator()
            menu.addAction("Export Selected", self._export_selected)
        menu.exec(
            self._export_btn.mapToGlobal(self._export_btn.rect().bottomLeft())
        )

    def _export_all(self) -> None:
        events = self._manager.query(limit=0)
        if not events:
            QMessageBox.information(self, "Export", "No events to export.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export All Events", "events.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        if ".xlsx" in selected_filter or path.endswith(".xlsx"):
            self._exporter.export_xlsx(events, path)
        else:
            self._exporter.export_csv(events, path)

    def _export_current_filter(self) -> None:
        filter_ = self._filters.to_filter()
        events = self._manager.query(filter_, limit=0)
        if not events:
            QMessageBox.information(self, "Export", "No events to export.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Filtered Events", "events.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        if ".xlsx" in selected_filter or path.endswith(".xlsx"):
            self._exporter.export_xlsx(events, path)
        else:
            self._exporter.export_csv(events, path)

    def _export_selected(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "Export", "No events selected.")
            return
        events = [e for e in self._model._events if e.id in ids]
        if not events:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Selected Events", "events.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        if ".xlsx" in selected_filter or path.endswith(".xlsx"):
            self._exporter.export_xlsx(events, path)
        else:
            self._exporter.export_csv(events, path)

    def _get_selected_ids(self) -> list[int]:
        ids: list[int] = []
        for idx in self._table.selectedIndexes():
            if idx.column() == 0:
                src_idx = self._map_to_source(idx)
                ev = self._model.event_at(src_idx.row())
                if ev is not None:
                    ids.append(ev.id)
        return list(set(ids))

    def _delete_selected(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "Delete", "No events selected.")
            return
        reply = QMessageBox.question(
            self, "Delete Events",
            f"Delete {len(ids)} selected event(s)?\n\n"
            f"Snapshot files will not be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_events(ids)
            self._refresh()

    def _delete_all(self) -> None:
        total = self._manager.count()
        if total == 0:
            QMessageBox.information(self, "Delete All", "No events to delete.")
            return
        reply = QMessageBox.question(
            self, "Delete All Events",
            f"Delete all {total} event(s)?\n\n"
            f"This action cannot be undone.\n"
            f"Snapshot files will not be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_all()
            self._refresh()
