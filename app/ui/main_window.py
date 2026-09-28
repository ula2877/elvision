"""
MainWindow — assembles all UI components and wires services together.

Startup sequence:
  1. Create services
  2. Create LayoutManager (single source of truth)
  3. Load saved layout into LayoutManager
  4. Build UI (Toolbar + Workspace receive LayoutManager reference)
  5. Connect signals (Toolbar → LayoutManager → Workspace)
  6. Load cameras (render with correct layout)
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QApplication,
    QMessageBox,
)

from app.ui.toolbar.toolbar import Toolbar
from app.ui.sidebar.sidebar import Sidebar
from app.ui.workspace.workspace import Workspace
from app.ui.widgets.status_bar import StatusBar
from app.ui.widgets.notification_manager import NotificationManager
from app.ui.widgets.toast import NotificationType
from app.ui.dialogs.add_camera import AddCameraDialog, DialogMode
from app.ui.dialogs.remove_confirm import RemoveConfirmDialog
from app.ui.dialogs.settings import SettingsDialog
from app.ui.styles import generate_dark_theme
from app.core.camera.manager import CameraManager
from app.core.ai.feature_manager import AIFeatureManager
from app.core.logging import LogService
from app.core.configuration import ConfigService
from app.core.layout.manager import LayoutManager
from app.core.settings.service import SettingsService
from app.core.services.snapshot import SnapshotService
from app.core.plugins import PluginManager
from app.core.groups.manager import GroupManager, ALL_CAMERAS_ID, UNGROUPED_ID
from app.core.events.manager import EventManager
from app.repositories.in_memory import InMemoryCameraRepository, InMemoryGroupRepository
from app.models import CameraInfo, LayoutGrid, CameraStatus
from app.ui.events.event_center_dialog import EventCenterDialog


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config_service: ConfigService) -> None:
        super().__init__()
        self._config_service = config_service

        # ── Step 1: Create services ───────────────────────
        self._settings_service = SettingsService()
        self._camera_manager = CameraManager()
        self._snapshot_service = SnapshotService()
        self._feature_manager: Optional[AIFeatureManager] = None  # created after UI
        self._plugin_manager = PluginManager()
        self._camera_repo = InMemoryCameraRepository()
        self._group_repo = InMemoryGroupRepository()
        self._group_manager = GroupManager(self._group_repo)
        self._group_manager.set_camera_ids_provider(
            self._camera_manager.registry.all_camera_ids
        )
        self._active_group_filter: Optional[str] = None

        # ── Step 2: Create LayoutManager (single source of truth) ──
        self._layout_manager = LayoutManager()

        # ── Step 3: Load saved layout into LayoutManager ──
        self._apply_saved_layout()

        # ── Event Center (created before UI because EventCenter needs EventManager) ──
        self._event_manager = EventManager(self)

        # ── Step 4: Build UI (Toolbar + Workspace get LayoutManager ref) ──
        self.setWindowTitle("Elvision \u2014 Video Management System")
        self.setMinimumSize(1280, 720)
        self.resize(1920, 1080)
        self._build_ui()
        self._sidebar.set_group_manager(self._group_manager)
        self._sidebar.set_camera_repo(self._camera_repo)

        # ── Step 5: Connect signals ───────────────────────
        self._connect_signals()

        # ── Step 6: Load cameras (layout is already correct) ──
        self._load_saved_cameras()
        self._apply_theme()

        # ── Fullscreen state restoration ─────────────────
        self._pre_fs_state: Qt.WindowState = Qt.WindowState.WindowNoState
        self._pre_fs_geo: Optional[object] = None

    # ── Layout persistence ────────────────────────────────

    def _apply_saved_layout(self) -> None:
        """Load layout from settings. Falls back to config default, then GRID_1X1."""
        saved = self._settings_service.get(
            "layout",
            self._config_service.config.default_layout,
        )
        try:
            grid = LayoutGrid[saved]
        except (KeyError, ValueError):
            grid = LayoutGrid.GRID_1X1
        self._layout_manager.set_grid(grid)

    def _save_layout(self, grid_name: str) -> None:
        self._settings_service.set("layout", grid_name)

    # ── UI construction ───────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar = Toolbar(self._layout_manager)
        root.addWidget(self._toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = Sidebar()
        self._workspace = Workspace(self._layout_manager)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._workspace)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([280, 1640])

        body.addWidget(self._splitter)
        root.addLayout(body)

        self._status_bar = StatusBar()
        root.addWidget(self._status_bar)

        self._notif_mgr = NotificationManager(self)

        # ── Event Center dialog (lazy-created) ──────────
        self._event_center_dialog: Optional[EventCenterDialog] = None

        # ── AI Feature Manager (needs workspace reference) ─────
        self._feature_manager = AIFeatureManager(
            self._camera_manager.registry,
            self._workspace,
            parent=self,
        )

    # ── Signal wiring ─────────────────────────────────────

    def _connect_signals(self) -> None:
        self._toolbar.settings_requested.connect(self._show_settings_dialog)
        self._toolbar.snapshot_requested.connect(self._take_snapshot)
        self._toolbar.record_requested.connect(self._toggle_recording)
        self._toolbar.refresh_requested.connect(self._refresh_all)
        self._toolbar.fullscreen_requested.connect(self._toggle_fullscreen)


        self._toolbar.layout_changed.connect(self._on_toolbar_layout_changed)

        self._sidebar.camera_selected.connect(self._on_camera_selected)
        self._sidebar.camera_double_clicked.connect(self._on_camera_double_clicked)
        self._sidebar.add_camera_requested.connect(self._show_add_camera_dialog)
        self._sidebar.edit_camera_requested.connect(self._show_edit_camera_dialog)
        self._sidebar.create_group_requested.connect(self._show_create_group_dialog)
        self._sidebar.edit_group_requested.connect(self._show_edit_group_dialog)
        self._sidebar.delete_group_requested.connect(self._delete_group)
        self._sidebar.group_selected.connect(self._on_group_selected)

        self._sidebar.hide_filter_requested.connect(self._on_hide_filter_requested)
        self._sidebar.camera_open_requested.connect(self._on_camera_open_requested)
        self._sidebar.camera_remove_requested.connect(self._on_camera_remove_requested)
        self._sidebar.camera_clear_selection_requested.connect(self._on_camera_clear_selection)
        self._sidebar.camera_assign_group_requested.connect(self._on_camera_assign_group)
        self._sidebar.camera_feature_toggled.connect(self._on_camera_feature_toggled)

        self._group_manager.group_list_changed.connect(self._refresh_group_list)

        self._workspace.camera_snapshot_requested.connect(self._take_snapshot_for)
        self._workspace.camera_fullscreen_requested.connect(self._on_camera_fullscreen)
        self._workspace.camera_reconnect_requested.connect(self._on_camera_reconnect)
        self._workspace.camera_settings_requested.connect(self._on_camera_settings)
        self._workspace.add_camera_requested.connect(self._show_add_camera_dialog)

        self._camera_manager.frame_received.connect(self._feature_manager.process_frame)
        self._camera_manager.camera_status_changed.connect(self._on_status_changed)
        self._camera_manager.stats_updated.connect(self._on_stats_updated)

        self._feature_manager.annotated_frame_ready.connect(self._on_annotated_frame)
        self._feature_manager.fall_alarm.connect(self._on_fall_alarm)
        self._feature_manager.fall_alarm_state.connect(self._on_fall_alarm_state)
        self._feature_manager.smoke_alarm.connect(self._on_smoke_alarm)
        self._feature_manager.smoke_alarm_state.connect(
            lambda cid, active: self._on_safety_alarm_state(cid, "smoke", active)
        )
        self._feature_manager.fire_alarm.connect(self._on_fire_alarm)
        self._feature_manager.fire_alarm_state.connect(
            lambda cid, active: self._on_safety_alarm_state(cid, "fire", active)
        )
        self._feature_manager.ppe_alarm.connect(self._on_ppe_alarm)
        self._feature_manager.ppe_alarm_state.connect(
            lambda cid, active: self._on_safety_alarm_state(cid, "ppe", active)
        )

        self._notif_mgr.toast_clicked.connect(self._on_toast_clicked)
        self._toolbar.event_center_requested.connect(self._on_notification_requested)

    # ── Layout: Toolbar → LayoutManager → Workspace ───────

    def _on_toolbar_layout_changed(self, grid_name: str) -> None:
        """User changed layout in toolbar combo.
        Flow: Toolbar emits → here → LayoutManager.set_grid → emits layout_changed → Workspace rebuilds."""
        try:
            grid = LayoutGrid[grid_name]
        except KeyError:
            return
        self._layout_manager.set_grid(grid)
        self._save_layout(grid_name)

    # ── Camera management ─────────────────────────────────

    def _load_saved_cameras(self) -> None:
        cameras = self._camera_repo.list_all()
        for info in cameras:
            self._add_camera_internal(info)
        self._refresh_group_list()

    def _add_camera_internal(self, info: CameraInfo) -> None:
        self._camera_repo.add(info)
        self._camera_repo.save()
        self._sidebar.add_camera(info)
        self._workspace.add_camera(info)
        try:
            self._camera_manager.add_camera(info)
            if self._feature_manager is not None:
                self._feature_manager.start_camera(info)
        except Exception as exc:
            self._status_bar.set_status(f"Error: {exc}")
        self._update_counts()
        self._refresh_group_list()

    def _show_add_camera_dialog(self) -> None:
        dialog = AddCameraDialog(self)
        dialog.camera_added.connect(self._add_camera_internal)
        dialog.exec()

    def _show_edit_camera_dialog(self, camera_id: str) -> None:
        """Open Edit Camera dialog pre-populated with existing CameraInfo."""
        info = self._camera_repo.get_by_id(camera_id)
        if info is None:
            self._status_bar.set_status("Camera not found")
            return
        groups = [(g.id, g.name) for g in self._group_manager.list_all()]
        current_group_id = info.group_ids[0] if info.group_ids else None
        dialog = AddCameraDialog(
            self,
            mode=DialogMode.EDIT,
            camera_info=info,
            groups=groups,
            current_group_id=current_group_id,
        )
        dialog.camera_edited.connect(self._on_camera_edited)
        dialog.exec()

    def _on_camera_edited(self, updated_info: CameraInfo) -> None:
        """Handle saved edits from the Edit Camera dialog.

        Flow:
        1. Compare old vs new to decide if stream restart is needed
        2. Update CameraRepository + save
        3. Update Sidebar display
        4. If group changed → update GroupManager assignment
        5. If URI or source_type changed → stop old worker, recreate source, restart
        6. If features changed → update AI workers at runtime
        7. Otherwise (name-only change) → just update display, no restart
        """
        camera_id = updated_info.id
        old_info = self._camera_repo.get_by_id(camera_id)
        if old_info is None:
            return

        # Determine if stream restart is needed
        stream_config_changed = (
            old_info.uri != updated_info.uri
            or old_info.source_type != updated_info.source_type
            or old_info.username != updated_info.username
            or old_info.password != updated_info.password
        )

        # Determine if features changed
        features_changed = (
            old_info.enabled_features != updated_info.enabled_features
        )

        # Determine if group changed
        old_group = old_info.group_ids[0] if old_info.group_ids else None
        new_group = updated_info.group_ids[0] if updated_info.group_ids else None
        group_changed = old_group != new_group

        # Update repository and persist
        self._camera_repo.update(updated_info)
        self._camera_repo.save()

        # Update sidebar display (name, type, detail line)
        widget = self._sidebar._camera_items.get(camera_id)
        if widget is not None:
            widget.update_info(updated_info)

        # Update group assignment in GroupManager
        if group_changed:
            try:
                self._group_manager.set_camera_group(camera_id, new_group or None)
                updated_info.group_ids = [new_group] if new_group else []
                self._camera_repo.update(updated_info)
                self._camera_repo.save()
                self._refresh_group_list()
                self._reapply_group_filter()
            except Exception as exc:
                self._status_bar.set_status("Error updating group: %s" % exc)

        if stream_config_changed:
            # Stop existing worker, replace source, restart
            try:
                if self._feature_manager is not None:
                    self._feature_manager.stop_camera(camera_id)
                self._camera_manager.remove_camera(camera_id)
                self._camera_manager.add_camera(updated_info)
                if self._feature_manager is not None:
                    self._feature_manager.start_camera(updated_info)
                self._status_bar.set_status(
                    "Camera \"%s\" updated — stream restarted" % updated_info.name
                )
            except Exception as exc:
                self._status_bar.set_status("Error restarting: %s" % exc)
        elif features_changed and self._feature_manager is not None:
            self._feature_manager.update_camera_features(updated_info)
            self._status_bar.set_status(
                "Camera \"%s\" updated — AI features changed" % updated_info.name
            )
        else:
            self._status_bar.set_status(
                "Camera \"%s\" updated" % updated_info.name
            )

    # ── Group management ──────────────────────────────────

    def _refresh_group_list(self) -> None:
        """Rebuild the sidebar groups list from GroupManager."""
        groups = self._group_manager.get_cameras_for_display()
        self._sidebar.set_groups(groups)

    def _show_create_group_dialog(self) -> None:
        from app.ui.dialogs.group_dialogs import CreateGroupDialog
        dialog = CreateGroupDialog(self)
        dialog.group_created.connect(self._on_group_created)
        dialog.exec()

    def _on_group_created(self, group_data) -> None:
        """Handle new group creation from dialog."""
        try:
            group = self._group_manager.create_group(
                name=group_data.name,
                description=group_data.description,
            )
            self._refresh_group_list()
            self._status_bar.set_status("Group \"%s\" created" % group.name)
        except ValueError as exc:
            QMessageBox.warning(self, "Create Group", str(exc))

    def _show_edit_group_dialog(self, group_id: str) -> None:
        group = self._group_manager.get(group_id)
        if group is None:
            return
        from app.ui.dialogs.group_dialogs import EditGroupDialog
        dialog = EditGroupDialog(group, self)
        dialog.group_edited.connect(lambda g: self._on_group_edited(g))
        dialog.exec()

    def _on_group_edited(self, updated_group) -> None:
        """Handle group edit from dialog."""
        try:
            self._group_manager.update_group(
                group_id=updated_group.id,
                name=updated_group.name,
                description=updated_group.description,
            )
            self._refresh_group_list()
            self._status_bar.set_status("Group \"%s\" updated" % updated_group.name)
        except ValueError as exc:
            QMessageBox.warning(self, "Edit Group", str(exc))

    def _delete_group(self, group_id: str) -> None:
        group = self._group_manager.get(group_id)
        if group is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete Group",
            "Delete group \"%s\"?\n\nCameras will not be deleted." % group.name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._group_manager.delete_group(group_id)
            self._refresh_group_list()
            if self._active_group_filter == group_id:
                self._active_group_filter = None
                self._workspace.clear_group_filter()
                self._sidebar.hide_filter_indicator()
            self._status_bar.set_status("Group deleted")

    def _on_group_selected(self, group_id: str) -> None:
        """Handle group selection in sidebar — filter workspace cameras."""
        self._active_group_filter = group_id

        if group_id == ALL_CAMERAS_ID or group_id is None:
            self._workspace.clear_group_filter()
            self._sidebar.hide_filter_indicator()
            self._status_bar.set_status("All cameras")
        elif group_id == UNGROUPED_ID:
            # Cameras not in any user group
            all_user_camera_ids = set()
            for g in self._group_manager.list_all():
                all_user_camera_ids.update(g.camera_ids)
            all_workspace_ids = set(self._workspace._camera_order)
            visible_ids = all_workspace_ids - all_user_camera_ids
            self._workspace.set_group_filter(visible_ids)
            self._sidebar.show_filter_indicator("Ungrouped")
            self._sidebar.hide_filter_indicator()
            self._status_bar.set_status("Showing: Ungrouped")
        else:
            visible_ids = set(self._group_manager.get_camera_ids(group_id))
            self._workspace.set_group_filter(visible_ids)
            group = self._group_manager.get(group_id)
            group_name = group.name if group else group_id
            self._sidebar.show_filter_indicator(group_name)
            self._sidebar.hide_filter_indicator()
            self._status_bar.set_status("Showing: %s" % group_name)

    def _on_hide_filter_requested(self) -> None:
        """Handle 'Clear Filter' — restore All Cameras view in workspace."""
        self._active_group_filter = None
        self._workspace.clear_group_filter()
        self._sidebar.hide_filter_indicator()
        self._status_bar.set_status("Filter cleared")

    def _reapply_group_filter(self) -> None:
        """Re-apply the current group filter (called after group list changes)."""
        gid = self._active_group_filter
        if gid is not None:
            if gid == ALL_CAMERAS_ID:
                self._workspace.clear_group_filter()
            else:
                self._on_group_selected(gid)

    # ── Context menu actions ──────────────────────────────

    def _on_camera_open_requested(self, camera_ids: list[str]) -> None:
        """Handle Open action from context menu — reserved for future."""
        pass

    def _on_camera_remove_requested(self, camera_ids: list[str]) -> None:
        """Handle Remove action from context menu — reuse existing removal flow."""
        if not camera_ids:
            return

        # Build list of (CameraInfo, CameraStatus) for confirmation dialog
        cameras_for_dialog: list[tuple[CameraInfo, CameraStatus]] = []
        for cam_id in camera_ids:
            info = self._camera_repo.get_by_id(cam_id)
            if info is None:
                continue
            state = self._camera_manager.get_state(cam_id)
            from app.models import camera_state_to_status
            status = camera_state_to_status(state)
            cameras_for_dialog.append((info, status))

        if not cameras_for_dialog:
            self._status_bar.set_status("No valid cameras to remove")
            return

        # Show confirmation dialog
        dialog = RemoveConfirmDialog(cameras_for_dialog, self)
        result = dialog.exec()

        if result != RemoveConfirmDialog.DialogCode.Accepted:
            self._status_bar.set_status("Removal cancelled")
            return

        # Remove each camera
        log = LogService.instance()
        removed_count = 0
        for cam_id in camera_ids:
            try:
                if self._feature_manager is not None:
                    self._feature_manager.stop_camera(cam_id)
                self._group_manager.remove_camera_from_all_groups(cam_id)
                self._camera_manager.remove_camera(cam_id)
                self._camera_repo.remove(cam_id)
                self._sidebar.remove_camera(cam_id)
                self._workspace.remove_camera(cam_id)
                removed_count += 1
                log.info("Camera removed: %s", cam_id)
            except Exception as exc:
                log.error("Failed to remove camera %s: %s", cam_id, exc)
                self._status_bar.set_status(f"Error removing {cam_id}: {exc}")

        self._camera_repo.save()
        self._update_counts()
        self._refresh_group_list()

        if removed_count > 0:
            self._status_bar.set_status(
                "%d camera%s removed" % (removed_count, "s" if removed_count != 1 else "")
            )

    def _on_camera_clear_selection(self) -> None:
        """Handle Clear Selection action from context menu."""
        self._sidebar.clear_checked()

    def _on_camera_assign_group(self, camera_ids: list[str], group_id: str) -> None:
        """Handle Assign Group action from context menu — immediate assignment."""
        target = group_id or None
        assigned = 0
        for cam_id in camera_ids:
            try:
                self._group_manager.set_camera_group(cam_id, target)
                info = self._camera_repo.get_by_id(cam_id)
                if info is not None:
                    info.group_ids = [target] if target else []
                    self._camera_repo.update(info)
                assigned += 1
            except Exception as exc:
                self._status_bar.set_status("Error assigning %s: %s" % (cam_id, exc))
        self._camera_repo.save()
        self._refresh_group_list()
        self._reapply_group_filter()
        if assigned:
            target_group = self._group_manager.get(target) if target else None
            label = target_group.name if target_group else "Ungrouped"
            self._status_bar.set_status(
                "%d camera%s assigned to \"%s\""
                % (assigned, "s" if assigned != 1 else "", label)
            )

    def _on_camera_feature_toggled(
        self, camera_ids: list[str], feature_key: str, enabled: bool
    ) -> None:
        """Handle Features submenu toggle — update enabled_features for each camera."""
        updated = 0
        for cam_id in camera_ids:
            info = self._camera_repo.get_by_id(cam_id)
            if info is None:
                continue
            if enabled:
                if feature_key not in info.enabled_features:
                    info.enabled_features.append(feature_key)
                    updated += 1
            else:
                if feature_key in info.enabled_features:
                    info.enabled_features.remove(feature_key)
                    updated += 1
        if updated:
            self._camera_repo.save()
            # Reconcile AI workers with updated feature list
            if self._feature_manager is not None:
                for cam_id in camera_ids:
                    info = self._camera_repo.get_by_id(cam_id)
                    if info is not None:
                        self._feature_manager.update_camera_features(info)
            from app.core.ai.registry import AIFeatureRegistry
            feature = AIFeatureRegistry.get(feature_key)
            label = feature.name if feature else feature_key
            state = "enabled" if enabled else "disabled"
            self._status_bar.set_status(
                "%s %s for %d camera%s"
                % (label, state, updated, "s" if updated != 1 else "")
            )

    # ── Removal flow (checkbox-based) ─────────────────────

    def _remove_checked_cameras(self) -> None:
        """Remove all cameras checked in the sidebar.

        Flow:
        1. Get checked camera IDs from sidebar
        2. If none, show warning dialog and return
        3. Build camera info list for confirmation
        4. Show RemoveConfirmDialog
        5. If confirmed, remove each camera:
           a. CameraManager.remove_camera (stops worker, thread, source)
           b. CameraRepository.remove + save
           c. Sidebar.remove_camera
           d. Workspace.remove_camera
        6. Update counts
        """
        checked_ids = self._sidebar.get_checked_ids()
        if not checked_ids:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("No Camera Selected")
            msg.setText("Please select at least one camera before removing.")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            return

        # Build list of (CameraInfo, CameraStatus) for confirmation dialog
        cameras_for_dialog: list[tuple[CameraInfo, CameraStatus]] = []
        for cam_id in checked_ids:
            info = self._camera_repo.get_by_id(cam_id)
            if info is None:
                continue
            state = self._camera_manager.get_state(cam_id)
            from app.models import camera_state_to_status
            status = camera_state_to_status(state)
            cameras_for_dialog.append((info, status))

        if not cameras_for_dialog:
            self._status_bar.set_status("No valid cameras to remove")
            return

        # Show confirmation dialog
        dialog = RemoveConfirmDialog(cameras_for_dialog, self)
        result = dialog.exec()

        if result != RemoveConfirmDialog.DialogCode.Accepted:
            self._status_bar.set_status("Removal cancelled")
            return

        # Remove each camera
        log = LogService.instance()
        removed_count = 0
        for cam_id in checked_ids:
            try:
                if self._feature_manager is not None:
                    self._feature_manager.stop_camera(cam_id)
                self._group_manager.remove_camera_from_all_groups(cam_id)
                self._camera_manager.remove_camera(cam_id)
                self._camera_repo.remove(cam_id)
                self._sidebar.remove_camera(cam_id)
                self._workspace.remove_camera(cam_id)
                removed_count += 1
                log.info("Camera removed: %s", cam_id)
            except Exception as exc:
                log.error("Failed to remove camera %s: %s", cam_id, exc)
                self._status_bar.set_status(f"Error removing {cam_id}: {exc}")

        self._camera_repo.save()
        self._update_counts()
        self._refresh_group_list()

        if removed_count > 0:
            self._status_bar.set_status(
                "%d camera%s removed" % (removed_count, "s" if removed_count != 1 else "")
            )

    def _on_camera_double_clicked(self, camera_id: str) -> None:
        """Handle double-click on camera in sidebar."""
        if self._layout_manager.is_fullscreen:
            self._layout_manager.exit_fullscreen()
            self._toolbar.set_fullscreen_active(False)
            self._status_bar.set_status("Exited fullscreen")
        else:
            self._layout_manager.enter_fullscreen(camera_id)
            self._toolbar.set_fullscreen_active(True)
            self._status_bar.set_status(f"Fullscreen: {camera_id}")

    # ── Actions ───────────────────────────────────────────

    def _take_snapshot(self) -> None:
        self._status_bar.set_status("Snapshot taken")

    def _take_snapshot_for(self, camera_id: str) -> None:
        self._status_bar.set_status(f"Snapshot: {camera_id}")

    def _toggle_recording(self) -> None:
        self._status_bar.set_status("Recording toggled")

    def _show_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._config_service.config, self)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self, changes: dict) -> None:
        self._config_service.update(**changes)
        self._status_bar.set_status("Settings saved")

    def _refresh_all(self) -> None:
        if self._feature_manager is not None:
            self._feature_manager.stop_all()
        self._camera_manager.stop_all()
        self._camera_manager.start_all()
        # Restart AI workers for cameras that have features enabled
        if self._feature_manager is not None:
            for info in self._camera_repo.list_all():
                if info.enabled_features:
                    self._feature_manager.start_camera(info)
        self._status_bar.set_status("Refreshed")

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            # ── Exit fullscreen → restore previous state ──
            self.setWindowState(self._pre_fs_state)
            if self._pre_fs_state != Qt.WindowState.WindowMaximized:
                # Only restore geometry if we were NOT maximized
                if self._pre_fs_geo is not None:
                    self.setGeometry(self._pre_fs_geo)
            self._pre_fs_geo = None
            self._pre_fs_state = Qt.WindowState.WindowNoState
            self._recalculate_workspace()
        else:
            # ── Enter fullscreen → save current state ─────
            self._pre_fs_state = self.windowState()
            self._pre_fs_geo = self.geometry()
            self.showFullScreen()
            self._recalculate_workspace()

    def _on_camera_fullscreen(self, camera_id: str) -> None:
        if self._layout_manager.is_fullscreen:
            self._status_bar.set_status(f"Fullscreen: {camera_id}")
        else:
            self._status_bar.set_status("Exited fullscreen")

    def _on_camera_reconnect(self, camera_id: str) -> None:
        self._camera_manager.restart_camera(camera_id)
        self._status_bar.set_status(f"Reconnecting: {camera_id}")

    def _on_camera_settings(self, camera_id: str) -> None:
        self._show_edit_camera_dialog(camera_id)

    def _on_camera_selected(self, camera_id: str) -> None:
        self._status_bar.set_status(f"Selected: {camera_id}")

    def _on_search(self, text: str) -> None:
        pass

    def _on_status_changed(self, camera_id: str, status: CameraStatus) -> None:
        self._workspace.set_camera_status(camera_id, status)
        self._sidebar.set_camera_status(camera_id, status)
        self._update_counts()

    def _on_stats_updated(self, stats) -> None:
        pass

    def _on_annotated_frame(self, frame_data) -> None:
        from app.models import FrameData
        if isinstance(frame_data, FrameData):
            self._event_manager.cache_frame(frame_data.camera_id, frame_data.data)

    def _on_fall_alarm(self, camera_id: str) -> None:
        info = self._camera_repo.get_by_id(camera_id)
        name = info.name if info else camera_id

        group_name = ""
        if info and info.group_ids:
            first_group = info.group_ids[0]
            group = self._group_manager.get(first_group)
            if group is not None:
                group_name = group.name

        self._event_manager.add_event(
            event_type="fall_detection",
            camera_id=camera_id,
            camera_name=name,
            group_name=group_name,
        )

        self._notif_mgr.show_notification(
            camera_id=camera_id,
            title=f"Fall Detected \u2014  {name}",
            notif_type=NotificationType.fall_detection(),
        )

    def _on_smoke_alarm(self, camera_id: str) -> None:
        info = self._camera_repo.get_by_id(camera_id)
        name = info.name if info else camera_id

        group_name = ""
        if info and info.group_ids:
            first_group = info.group_ids[0]
            group = self._group_manager.get(first_group)
            if group is not None:
                group_name = group.name

        self._event_manager.add_event(
            event_type="smoke",
            camera_id=camera_id,
            camera_name=name,
            group_name=group_name,
        )

        self._notif_mgr.show_notification(
            camera_id=camera_id,
            title=f"Smoke Detected \u2014 {name}",
            notif_type=NotificationType.smoke(),
        )

    def _on_fire_alarm(self, camera_id: str) -> None:
        info = self._camera_repo.get_by_id(camera_id)
        name = info.name if info else camera_id

        group_name = ""
        if info and info.group_ids:
            first_group = info.group_ids[0]
            group = self._group_manager.get(first_group)
            if group is not None:
                group_name = group.name

        self._event_manager.add_event(
            event_type="fire",
            camera_id=camera_id,
            camera_name=name,
            group_name=group_name,
        )

        self._notif_mgr.show_notification(
            camera_id=camera_id,
            title=f"Fire Detected \u2014 {name}",
            notif_type=NotificationType.fire(),
        )

    def _on_ppe_alarm(self, camera_id: str, detail: str) -> None:
        info = self._camera_repo.get_by_id(camera_id)
        name = info.name if info else camera_id

        group_name = ""
        if info and info.group_ids:
            first_group = info.group_ids[0]
            group = self._group_manager.get(first_group)
            if group is not None:
                group_name = group.name

        self._event_manager.add_event(
            event_type="ppe",
            camera_id=camera_id,
            camera_name=name,
            group_name=group_name,
            notes=detail,
        )

        self._notif_mgr.show_notification(
            camera_id=camera_id,
            title=f"PPE Violation \u2014 {name}",
            notif_type=NotificationType.ppe(),
        )

    def _on_toast_clicked(self, camera_id: str) -> None:
        if self._layout_manager.is_fullscreen:
            if self._layout_manager.fullscreen_camera_id == camera_id:
                self._layout_manager.exit_fullscreen()
                self._toolbar.set_fullscreen_active(False)
                self._status_bar.set_status("Exited fullscreen")
            else:
                self._layout_manager.switch_fullscreen(camera_id)
                self._status_bar.set_status(f"Fullscreen: {camera_id}")
        else:
            self._layout_manager.enter_fullscreen(camera_id)
            self._toolbar.set_fullscreen_active(True)
            self._status_bar.set_status(f"Fullscreen: {camera_id}")

    def _on_notification_requested(self) -> None:
        if self._event_center_dialog is None:
            self._event_center_dialog = EventCenterDialog(
                self._event_manager, self
            )
        if self._event_center_dialog.isVisible():
            self._event_center_dialog.raise_()
            self._event_center_dialog.activateWindow()
        else:
            self._event_center_dialog.showMaximized()

    def _on_fall_alarm_state(self, camera_id: str, active: bool) -> None:
        widget = self._workspace.get_widget(camera_id)
        if widget is not None:
            widget.set_alarm(active)

    def _on_safety_alarm_state(self, camera_id: str, category: str, active: bool) -> None:
        widget = self._workspace.get_widget(camera_id)
        if widget is not None:
            widget.set_alarm(active)

    def _update_counts(self) -> None:
        """Recompute all status counters from the single source of truth (CameraRegistry).

        Every UI component (StatusBar, Sidebar) receives the same values.
        No widget computes its own counters independently.
        """
        registry = self._camera_manager.registry
        summary = registry.status_summary()

        total = summary["total"]
        online = summary["online"]
        offline = summary["offline"] + summary["error"]

        self._status_bar.update_counts(total, online, offline)
        self._sidebar.update_counts(total, online)

    def _apply_theme(self) -> None:
        self.setStyleSheet(generate_dark_theme())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recalculate_workspace()

    def _recalculate_workspace(self) -> None:
        """Push the current Workspace size into LayoutManager and rebuild grid."""
        ws = self._workspace.size()
        if ws.width() > 0 and ws.height() > 0:
            self._layout_manager.set_workspace_size(ws)
            self._layout_manager.layout_changed.emit(
                self._layout_manager.current_grid.name
            )

    def closeEvent(self, event) -> None:
        log = LogService.instance()
        log.info("MainWindow closing — stopping all cameras")
        if self._feature_manager is not None:
            self._feature_manager.stop_all()
        self._camera_manager.stop_all()
        if self._event_center_dialog is not None:
            self._event_center_dialog.close()
        self._event_manager.shutdown()
        self._camera_repo.save()
        self._group_manager.save()
        self._plugin_manager.load_all()
        log.info("MainWindow closed")
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._layout_manager.is_fullscreen:
            self._workspace.exit_fullscreen()
            self._toolbar.set_fullscreen_active(False)
            self._status_bar.set_status("Exited fullscreen")
            return
        super().keyPressEvent(event)
