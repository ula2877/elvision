"""
GroupManager — business logic for camera group CRUD.

Responsibilities:
    - Create, edit, delete groups
    - Enforce built-in group protection (All Cameras, Ungrouped)
    - Enforce unique names
    - Assign / unassign cameras to groups
    - Provide group filtering for sidebar display
    - Persist via GroupRepository

Virtual Groups:
    "All Cameras" and "Ungrouped" are NOT stored in the repository.
    They are calculated dynamically from CameraRegistry.
    Their camera counts are always current.

Architecture:
    GroupManager is a pure service — no Qt dependency except QObject for signals.
    MainWindow owns the single instance and wires it to the Sidebar.
"""
from __future__ import annotations

import time as _time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from app.core.logging import LogService
from app.models import CameraGroup
from app.repositories import GroupRepository


# ── Virtual group constants ─────────────────────────────────────────────────

ALL_CAMERAS_ID = "__all__"
UNGROUPED_ID = "__ungrouped__"

_VIRTUAL_IDS = {ALL_CAMERAS_ID, UNGROUPED_ID}


class GroupManager(QObject):
    """Manages camera groups with persistence and virtual group support.

    Signals:
        group_created(CameraGroup)       — new group added
        group_updated(CameraGroup)       — group edited
        group_deleted(str)               — group removed (group_id)
        group_list_changed()             — any structural change (rebuild list)
        camera_assigned(str, str)        — (camera_id, group_id)
        camera_unassigned(str, str)      — (camera_id, group_id)
    """

    group_created = Signal(object)
    group_updated = Signal(object)
    group_deleted = Signal(str)
    group_list_changed = Signal()
    camera_assigned = Signal(str, str)
    camera_unassigned = Signal(str, str)

    def __init__(self, repo: GroupRepository, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._log = LogService.instance()
        self._camera_ids_fn: Optional[Callable[[], list[str]]] = None

    def set_camera_ids_provider(self, fn: Callable[[], list[str]]) -> None:
        """Set the callable that returns all registered camera IDs.

        Called by MainWindow after CameraManager is initialized.
        The callable should return CameraRegistry.all_camera_ids().
        """
        self._camera_ids_fn = fn

    # ── Virtual group queries (dynamic, not from repo) ──────────────────

    def _all_camera_ids(self) -> list[str]:
        """Return all camera IDs from the registry via the provider."""
        if self._camera_ids_fn is not None:
            return self._camera_ids_fn()
        return []

    def _user_group_camera_ids(self) -> set[str]:
        """Return the set of camera IDs that belong to any user group."""
        ids: set[str] = set()
        for g in self._repo.list_all():
            ids.update(g.camera_ids)
        return ids

    def _ungrouped_camera_ids(self) -> list[str]:
        """Return camera IDs that are not in any user group."""
        user_ids = self._user_group_camera_ids()
        return [cid for cid in self._all_camera_ids() if cid not in user_ids]

    def get_virtual_group_count(self, group_id: str) -> int:
        """Return the dynamic camera count for a virtual group."""
        if group_id == ALL_CAMERAS_ID:
            return len(self._all_camera_ids())
        if group_id == UNGROUPED_ID:
            return len(self._ungrouped_camera_ids())
        return 0

    # ── Query ─────────────────────────────────────────────────────────────

    def list_all(self) -> list[CameraGroup]:
        """Return all user groups (never includes virtual groups)."""
        return list(self._repo.list_all())

    def get(self, group_id: str) -> Optional[CameraGroup]:
        return self._repo.get_by_id(group_id)

    def get_camera_ids(self, group_id: str) -> list[str]:
        """Return camera IDs for a group. Virtual groups return dynamic results."""
        if group_id == ALL_CAMERAS_ID:
            return self._all_camera_ids()
        if group_id == UNGROUPED_ID:
            return self._ungrouped_camera_ids()
        group = self._repo.get_by_id(group_id)
        return list(group.camera_ids) if group else []

    def get_cameras_for_display(self) -> list[dict]:
        """Return groups formatted for sidebar display.

        Virtual groups are prepended with dynamically calculated counts.
        User groups follow with their stored camera_ids counts.
        Sorted: virtual first, then favorites, then alphabetical.
        """
        result = []

        # Virtual groups (dynamic counts)
        result.append({
            "id": ALL_CAMERAS_ID,
            "name": "All Cameras",
            "camera_count": len(self._all_camera_ids()),
            "is_builtin": True,
            "is_virtual": True,
            "icon": "camera",
            "color": "",
            "is_favorite": True,
        })
        result.append({
            "id": UNGROUPED_ID,
            "name": "Ungrouped",
            "camera_count": len(self._ungrouped_camera_ids()),
            "is_builtin": True,
            "is_virtual": True,
            "icon": "inbox",
            "color": "",
            "is_favorite": True,
        })

        # User groups (stored counts)
        for g in self._repo.list_all():
            result.append({
                "id": g.id,
                "name": g.name,
                "camera_count": len(g.camera_ids),
                "is_builtin": False,
                "is_virtual": False,
                "icon": g.icon,
                "color": g.color,
                "is_favorite": g.is_favorite,
            })

        result.sort(key=lambda x: (not x["is_virtual"], not x["is_favorite"], x["name"]))
        return result

    def get_group_for_camera(self, camera_id: str) -> Optional[str]:
        """Return the user group_id that contains this camera, or None."""
        for g in self._repo.list_all():
            if camera_id in g.camera_ids:
                return g.id
        return None

    def is_virtual(self, group_id: str) -> bool:
        """Check if a group_id is a virtual system group."""
        return group_id in _VIRTUAL_IDS

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create_group(self, name: str, description: str = "", color: str = "") -> CameraGroup:
        """Create a new group. Raises ValueError if name is duplicate."""
        name = name.strip()
        if not name:
            raise ValueError("Group name cannot be empty")
        if self._name_exists(name):
            raise ValueError("A group with this name already exists")

        now = _time.time()
        group = CameraGroup(
            id=str(int(now * 1000))[-8:],
            name=name,
            description=description.strip(),
            color=color,
            created_at=now,
            updated_at=now,
        )
        self._repo.add(group)
        self._repo.save()
        self._log.info("Group created: %s (%s)", group.id, group.name)
        self.group_created.emit(group)
        self.group_list_changed.emit()
        return group

    def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> CameraGroup:
        """Update group fields. Raises ValueError on bad name or virtual group."""
        group = self._repo.get_by_id(group_id)
        if group is None:
            raise ValueError("Group not found")
        if group_id in _VIRTUAL_IDS:
            raise ValueError("Cannot modify virtual groups")

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Group name cannot be empty")
            if self._name_exists(name, exclude_id=group_id):
                raise ValueError("A group with this name already exists")
            group.name = name

        if description is not None:
            group.description = description.strip()
        if color is not None:
            group.color = color

        group.updated_at = _time.time()
        self._repo.update(group)
        self._repo.save()
        self._log.info("Group updated: %s (%s)", group.id, group.name)
        self.group_updated.emit(group)
        self.group_list_changed.emit()
        return group

    def delete_group(self, group_id: str) -> None:
        """Delete a group. Virtual groups cannot be deleted."""
        if group_id in _VIRTUAL_IDS:
            self._log.warning("Cannot delete virtual group: %s", group_id)
            return
        group = self._repo.get_by_id(group_id)
        if group is None:
            return

        self._repo.remove(group_id)
        self._repo.save()
        self._log.info("Group deleted: %s (%s)", group_id, group.name)
        self.group_deleted.emit(group_id)
        self.group_list_changed.emit()

    # ── Camera assignment ────────────────────────────────────────────────

    def assign_camera(self, camera_id: str, group_id: str) -> None:
        """Add a camera to a user group. Virtual groups rejected."""
        if group_id in _VIRTUAL_IDS:
            return
        group = self._repo.get_by_id(group_id)
        if group is None:
            return
        if camera_id in group.camera_ids:
            return
        group.camera_ids.append(camera_id)
        group.updated_at = _time.time()
        self._repo.update(group)
        self._repo.save()
        self.camera_assigned.emit(camera_id, group_id)
        self.group_list_changed.emit()

    def unassign_camera(self, camera_id: str, group_id: str) -> None:
        """Remove a camera from a user group. Virtual groups rejected."""
        if group_id in _VIRTUAL_IDS:
            return
        group = self._repo.get_by_id(group_id)
        if group is None:
            return
        if camera_id not in group.camera_ids:
            return
        group.camera_ids.remove(camera_id)
        group.updated_at = _time.time()
        self._repo.update(group)
        self._repo.save()
        self.camera_unassigned.emit(camera_id, group_id)
        self.group_list_changed.emit()

    def set_camera_group(self, camera_id: str, new_group_id: Optional[str]) -> None:
        """Move a camera from its current group to a new one (or no group)."""
        current_id = self.get_group_for_camera(camera_id)
        if current_id == new_group_id:
            return
        if current_id is not None:
            self.unassign_camera(camera_id, current_id)
        if new_group_id is not None:
            self.assign_camera(camera_id, new_group_id)

    def get_camera_ids_for_filter(self, group_id: str) -> list[str]:
        """Return camera IDs to show for a given group filter.

        Virtual groups compute dynamically. User groups return stored IDs.
        """
        return self.get_camera_ids(group_id)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _name_exists(self, name: str, exclude_id: Optional[str] = None) -> bool:
        for g in self._repo.list_all():
            if g.id == exclude_id:
                continue
            if g.name.lower() == name.lower():
                return True
        return False

    def remove_camera_from_all_groups(self, camera_id: str) -> None:
        """Remove a camera ID from every user group it belongs to.

        Called when a camera is deleted from the system, so group
        camera_counts stay accurate.
        """
        changed = False
        for g in self._repo.list_all():
            if camera_id in g.camera_ids:
                g.camera_ids.remove(camera_id)
                g.updated_at = _time.time()
                self._repo.update(g)
                self.camera_unassigned.emit(camera_id, g.id)
                changed = True
        if changed:
            self._repo.save()
            self.group_list_changed.emit()

    def save(self) -> None:
        """Persist to disk. Called by MainWindow.closeEvent."""
        self._repo.save()
