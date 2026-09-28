from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QTableView,
    QHeaderView,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QMenu,
)

from app.core.events.manager import EventManager
from app.core.events.models import EventRecord, EventFilter, EVENT_STATUS_ACKNOWLEDGED
from app.ui.events.event_model import EventTableModel, COL_SNAPSHOT, COL_TIME
from app.ui.events.event_filters import EventFilters
from app.ui.events.event_detail import EventDetailDialog
from app.ui.events.exporter import EventExporter


_PAGE_SIZE = 500


class EventCenter(QDockWidget):
    def __init__(self, manager: EventManager, parent=None) -> None:
        super().__init__("Events", parent)
        self._manager = manager
        self._exporter = EventExporter()

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setMinimumWidth(800)

        self._build_ui()
        self._connect_signals()
        self._refresh()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top toolbar: filters (left) + actions (right) ──
        self._filters = EventFilters()
        tool_row = QHBoxLayout()
        tool_row.setContentsMargins(0, 0, 0, 0)
        tool_row.setSpacing(0)
        tool_row.addWidget(self._filters, 1)

        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(8, 4, 8, 4)
        action_bar.setSpacing(4)

        self._refresh_btn = QPushButton("\u21bb  Refresh")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(self._refresh)
        action_bar.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("Export  \u25be")
        self._export_btn.setFixedHeight(28)
        self._export_btn.clicked.connect(self._show_export_menu)
        action_bar.addWidget(self._export_btn)

        self._more_btn = QPushButton("\u22ee")
        self._more_btn.setFixedWidth(32)
        self._more_btn.setFixedHeight(28)
        self._more_btn.clicked.connect(self._show_more_menu)
        action_bar.addWidget(self._more_btn)

        tool_row.addLayout(action_bar)
        layout.addLayout(tool_row)

        # ── Table ──────────────────────────────────────────
        self._model = EventTableModel(self)
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().hide()
        self._table.setSortingEnabled(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        hdr.setHighlightSections(False)

        self._table.setColumnWidth(COL_SNAPSHOT, 52)
        self._table.setColumnWidth(COL_TIME, 80)

        self._table.setStyleSheet(
            "QTableView { background-color: #0F172A; alternate-background-color: #1E293B; "
            "color: #E2E8F0; border: none; font-size: 12px; } "
            "QTableView::item { padding: 4px 8px; border: none; } "
            "QTableView::item:selected { background-color: #1D4ED8; } "
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; "
            "padding: 6px 8px; border: none; border-bottom: 1px solid #334155; font-weight: 600; font-size: 11px; }"
        )

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        open_action = QAction("Open Detail", self._table)
        open_action.triggered.connect(self._open_selected_detail)
        self._table.addAction(open_action)

        delete_action = QAction("Delete", self._table)
        delete_action.triggered.connect(self._delete_selected)
        self._table.addAction(delete_action)

        export_action = QAction("Export Selected...", self._table)
        export_action.triggered.connect(self._export_selected)
        self._table.addAction(export_action)

        layout.addWidget(self._table)

        # ── Footer: count label ────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 4, 8, 4)

        self._count_label = QPushButton()
        self._count_label.setEnabled(False)
        self._count_label.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #94A3B8; font-size: 11px; }"
        )
        footer.addWidget(self._count_label)

        layout.addLayout(footer)

    def _connect_signals(self) -> None:
        self._filters.filter_changed.connect(self._refresh)
        self._table.doubleClicked.connect(self._open_selected_detail)
        self._manager.event_created.connect(self._on_new_event)
        self._table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    def _on_selection_changed(self) -> None:
        pass  # reserved for future dynamic button state

    # ── Refresh ────────────────────────────────────────────

    def _on_new_event(self, event: EventRecord) -> None:
        self._refresh()

    def _refresh(self) -> None:
        filter_ = self._filters.to_filter()
        total = self._manager.count(filter_)
        events = self._manager.query(filter_, limit=_PAGE_SIZE)
        self._model.set_events(events)
        self._count_label.setText(f"Events: {total}")

        cameras = self._manager.distinct_cameras()
        self._filters.set_camera_ids(cameras)

        groups = self._manager.distinct_groups()
        self._filters.set_group_names(groups)

    # ── Detail ─────────────────────────────────────────────

    def _open_selected_detail(self) -> None:
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        ev = self._model.event_at(idx.row())
        if ev is None:
            return
        dialog = EventDetailDialog(ev, self._manager, self)
        dialog.exec()
        self._refresh()

    # ── Export ──────────────────────────────────────────────

    def _show_export_menu(self) -> None:
        menu = QMenu(self._export_btn)
        menu.addAction("Export to Excel (.xlsx)", self._export_xlsx_all)
        menu.addAction("Export to CSV", self._export_csv_all)
        menu.addSeparator()
        menu.addAction("Export Current Filter", self._export_current_filter)
        menu.exec(self._export_btn.mapToGlobal(
            self._export_btn.rect().bottomLeft()
        ))

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

    def _export_csv_all(self) -> None:
        events = self._manager.query(limit=0)
        if not events:
            QMessageBox.information(self, "Export", "No events to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "events.csv", "CSV (*.csv)"
        )
        if path:
            self._exporter.export_csv(events, path)

    def _export_xlsx_all(self) -> None:
        events = self._manager.query(limit=0)
        if not events:
            QMessageBox.information(self, "Export", "No events to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Excel", "events.xlsx", "Excel (*.xlsx)"
        )
        if path:
            self._exporter.export_xlsx(events, path)

    def _export_selected(self) -> None:
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        ev = self._model.event_at(idx.row())
        if ev is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Event", "", "CSV (*.csv);;Excel (*.xlsx)"
        )
        if not path:
            return
        if path.endswith(".xlsx"):
            self._exporter.export_xlsx([ev], path)
        else:
            if not path.endswith(".csv"):
                path += ".csv"
            self._exporter.export_csv([ev], path)

    # ── Delete helpers ─────────────────────────────────────

    def _get_selected_ids(self) -> list[int]:
        ids: list[int] = []
        for idx in self._table.selectedIndexes():
            if idx.column() == 0:
                ev = self._model.event_at(idx.row())
                if ev is not None:
                    ids.append(ev.id)
        return ids

    def _filters_are_active(self) -> bool:
        f = self._filters.to_filter()
        return bool(f.search or f.date_from or f.date_to
                    or f.camera_id or f.group_name
                    or f.event_type or f.status)

    # ── More menu ──────────────────────────────────────────

    def _show_more_menu(self) -> None:
        selected = self._get_selected_ids()
        menu = QMenu(self._more_btn)

        del_sel = menu.addAction("Delete Selected")
        del_sel.setEnabled(len(selected) > 0)
        del_sel.triggered.connect(self._delete_selected)

        del_filt = menu.addAction("Delete Filtered")
        del_filt.triggered.connect(self._delete_filtered)

        menu.addSeparator()

        del_all = menu.addAction("Delete All Events")
        del_all.triggered.connect(self._delete_all)

        clear_ack = menu.addAction("Clear Acknowledged")
        clear_ack.triggered.connect(self._clear_acknowledged)

        menu.exec(self._more_btn.mapToGlobal(
            self._more_btn.rect().bottomLeft()
        ))

    def _delete_filtered(self) -> None:
        filter_ = self._filters.to_filter()
        total = self._manager.count(filter_)
        if total == 0:
            QMessageBox.information(self, "Delete", "No events match the current filter.")
            return
        reply = QMessageBox.question(
            self, "Delete Filtered",
            f"Delete all {total} event(s) matching the current filter?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_by_filter(filter_)
            self._refresh()

    def _clear_acknowledged(self) -> None:
        total = self._manager.count(
            EventFilter(status=EVENT_STATUS_ACKNOWLEDGED)
        )
        if total == 0:
            QMessageBox.information(self, "Clear Acknowledged",
                                    "No acknowledged events to clear.")
            return
        reply = QMessageBox.question(
            self, "Clear Acknowledged",
            f"Delete {total} acknowledged event(s)?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_by_status(EVENT_STATUS_ACKNOWLEDGED)
            self._refresh()

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
        remaining = self._manager.count()
        if remaining == 0:
            QMessageBox.information(self, "Delete All", "No events to delete.")
            return
        reply = QMessageBox.question(
            self, "Delete All Events",
            f"Delete all {remaining} event(s)?\n\n"
            f"This action cannot be undone.\n"
            f"Snapshot files will not be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_all()
            self._refresh()
