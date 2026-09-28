"""
CameraContextMenu — right-click context menu for camera operations.

Provides actions on the currently selected camera(s):
    Open (reserved)
    Settings... (single selection only)
    Assign Group > (submenu, dynamic from GroupManager)
    Features > (submenu, checkable items from AIFeatureRegistry)
    Remove (uses existing confirmation dialog)
    Clear Selection

The menu operates on the checked camera selection. If no other cameras are
checked, it acts only on the clicked camera.

Signals:
    open_requested(list[str])           — reserved for future
    settings_requested(str)             — single camera_id (only when 1 selected)
    assign_group_requested(list[str], str) — (camera_ids, group_id)
    feature_toggled(list[str], str, bool) — (camera_ids, feature_key, enabled)
    remove_requested(list[str])         — camera_ids to remove
    clear_selection_requested()         — uncheck all
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QWidget

from app.core.ai.registry import AIFeatureRegistry
from app.core.groups.manager import GroupManager, ALL_CAMERAS_ID, UNGROUPED_ID


_MENU_STYLE = (
    "QMenu { background: #1A1D27; border: 1px solid #2E3140; border-radius: 6px; padding: 4px; }"
    "QMenu::item { padding: 6px 16px; color: #E2E8F0; border-radius: 4px; }"
    "QMenu::item:selected { background: #3B82F6; color: white; }"
    "QMenu::item:disabled { color: #4B5060; }"
    "QMenu::separator { height: 1px; background: #2E3140; margin: 4px 8px; }"
)


class CameraContextMenu(QMenu):
    """Modern context menu for camera operations.

    Build dynamically on each show to reflect current group state.
    """

    open_requested = Signal(list)             # camera_ids (reserved)
    settings_requested = Signal(str)          # camera_id (single)
    assign_group_requested = Signal(list, str)  # (camera_ids, group_id)
    feature_toggled = Signal(list, str, bool)  # (camera_ids, feature_key, enabled)
    remove_requested = Signal(list)           # camera_ids
    clear_selection_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_MENU_STYLE)
        self._group_manager: Optional[GroupManager] = None
        self._camera_repo = None

    def set_group_manager(self, manager: GroupManager) -> None:
        """Set the GroupManager used to populate the Assign Group submenu."""
        self._group_manager = manager

    def set_camera_repo(self, repo) -> None:
        """Set the camera repository for reading enabled_features."""
        self._camera_repo = repo

    def build(
        self,
        clicked_camera_id: str,
        checked_ids: list[str],
    ) -> None:
        """Build the menu for the current selection context.

        Args:
            clicked_camera_id: The camera that was right-clicked.
            checked_ids: All currently checked camera IDs from the sidebar.
        """
        self.clear()

        # Determine effective selection: use checked if any, else just clicked
        if checked_ids:
            effective_ids = list(checked_ids)
        else:
            effective_ids = [clicked_camera_id]

        single_mode = len(effective_ids) == 1

        # ── Open (reserved) ──────────────────────────────
        open_action = QAction("Open", self)
        open_action.setEnabled(False)
        self.addAction(open_action)

        # ── Settings... ──────────────────────────────────
        settings_action = QAction("Settings...", self)
        settings_action.setEnabled(single_mode)
        if single_mode:
            settings_action.triggered.connect(
                lambda: self.settings_requested.emit(effective_ids[0])
            )
        self.addAction(settings_action)

        self.addSeparator()

        # ── Assign Group > ───────────────────────────────
        assign_menu = QMenu("Assign Group", self)
        assign_menu.setStyleSheet(_MENU_STYLE)

        if self._group_manager is not None:
            # None (Ungrouped)
            ungroup_action = QAction("None (Ungrouped)", assign_menu)
            ungroup_action.triggered.connect(
                lambda: self.assign_group_requested.emit(effective_ids, "")
            )
            assign_menu.addAction(ungroup_action)

            # Separator
            assign_menu.addSeparator()

            # User groups
            groups = self._group_manager.list_all()
            for group in groups:
                action = QAction(group.name, assign_menu)
                gid = group.id
                action.triggered.connect(
                    lambda checked=False, g=gid: self.assign_group_requested.emit(
                        effective_ids, g
                    )
                )
                assign_menu.addAction(action)

        self.addMenu(assign_menu)

        # ── Features > ────────────────────────────────
        features_menu = QMenu("Features", self)
        features_menu.setStyleSheet(_MENU_STYLE)

        grouped = AIFeatureRegistry.by_category()
        if grouped:
            # Gather enabled_features for each effective camera
            camera_features: list[set[str]] = []
            if self._camera_repo is not None:
                for cam_id in effective_ids:
                    info = self._camera_repo.get_by_id(cam_id)
                    if info is not None:
                        camera_features.append(set(info.enabled_features))
                    else:
                        camera_features.append(set())

            for category, cat_features in grouped.items():
                # Category header (disabled, bold)
                cat_action = QAction(category, features_menu)
                cat_action.setEnabled(False)
                font = cat_action.font()
                font.setBold(True)
                cat_action.setFont(font)
                features_menu.addAction(cat_action)

                for feature in cat_features:
                    if feature.available:
                        label = feature.name
                        action = QAction(label, features_menu)
                        action.setCheckable(True)
                        all_enabled = (
                            all(feature.key in cf for cf in camera_features)
                            if camera_features
                            else False
                        )
                        action.setChecked(all_enabled)
                        fk = feature.key
                        action.triggered.connect(
                            lambda checked, key=fk: self.feature_toggled.emit(
                                effective_ids, key, checked
                            )
                        )
                    else:
                        label = "%s (Coming Soon)" % feature.name
                        action = QAction(label, features_menu)
                        action.setEnabled(False)
                    features_menu.addAction(action)

                features_menu.addSeparator()

            # Remove trailing separator
            last_action = features_menu.actions()[-1]
            if last_action and last_action.isSeparator():
                features_menu.removeAction(last_action)
        else:
            no_action = QAction("No features available", features_menu)
            no_action.setEnabled(False)
            features_menu.addAction(no_action)

        self.addMenu(features_menu)

        self.addSeparator()

        # ── Remove ───────────────────────────────────────
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(
            lambda: self.remove_requested.emit(effective_ids)
        )
        self.addAction(remove_action)

        self.addSeparator()

        # ── Clear Selection ──────────────────────────────
        clear_action = QAction("Clear Selection", self)
        clear_action.triggered.connect(self.clear_selection_requested.emit)
        self.addAction(clear_action)
