"""
In-memory repository with JSON persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

from app.core.logging import LogService
from app.models import (
    CameraInfo,
    CameraGroup,
    SourceType,
    SourceConfig,
    TransportProtocol,
)
from app.repositories import CameraRepository, GroupRepository


class InMemoryCameraRepository(CameraRepository):
    """Camera repository backed by in-memory dict + JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or Path("cameras.json")
        self._cameras: dict[str, CameraInfo] = {}
        self._log = LogService.instance()
        self._load()

    def list_all(self) -> Sequence[CameraInfo]:
        return list(self._cameras.values())

    def get_by_id(self, camera_id: str) -> Optional[CameraInfo]:
        return self._cameras.get(camera_id)

    def add(self, camera: CameraInfo) -> None:
        self._cameras[camera.id] = camera
        self._log.info("Camera added: %s (%s)", camera.id, camera.name)

    def update(self, camera: CameraInfo) -> None:
        if camera.id in self._cameras:
            self._cameras[camera.id] = camera

    def remove(self, camera_id: str) -> None:
        self._cameras.pop(camera_id, None)
        self._log.info("Camera removed: %s", camera_id)

    def save(self) -> None:
        data = []
        for c in self._cameras.values():
            data.append({
                "id": c.id,
                "name": c.name,
                "uri": c.uri,
                "source_type": c.source_type.value,
                "username": c.username,
                "password": c.password,
                "location": c.location,
                "group_ids": c.group_ids,
                "width": c.width,
                "height": c.height,
                "fps": c.fps,
                "bitrate_kbps": c.bitrate_kbps,
                "auto_reconnect": c.auto_reconnect,
                "recording_enabled": c.recording_enabled,
                "ai_enabled": c.ai_enabled,
                "enabled_features": c.enabled_features,
                "snapshot_dir": c.snapshot_dir,
                "recording_dir": c.recording_dir,
                "source_config": {
                    "transport_protocol": c.source_config.transport_protocol.value,
                    "connection_timeout_sec": c.source_config.connection_timeout_sec,
                    "reconnect_interval_sec": c.source_config.reconnect_interval_sec,
                    "max_reconnect_attempts": c.source_config.max_reconnect_attempts,
                    "buffer_size": c.source_config.buffer_size,
                    "playback_speed": c.source_config.playback_speed,
                    "loop": c.source_config.loop,
                    "youtube_quality": c.source_config.youtube_quality,
                },
            })
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._log.info("Cameras saved (%d)", len(data))
        except Exception as exc:
            self._log.error("Failed to save cameras: %s", exc)

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                st_str = item.get("source_type", item.get("transport", "rtsp"))
                try:
                    source_type = SourceType(st_str)
                except ValueError:
                    source_type = SourceType.RTSP

                sc_data = item.get("source_config", {})
                tp_str = sc_data.get("transport_protocol", "auto")
                try:
                    tp = TransportProtocol(tp_str)
                except ValueError:
                    tp = TransportProtocol.AUTO

                source_config = SourceConfig(
                    transport_protocol=tp,
                    connection_timeout_sec=sc_data.get("connection_timeout_sec", 10.0),
                    reconnect_interval_sec=sc_data.get("reconnect_interval_sec", 5.0),
                    max_reconnect_attempts=sc_data.get("max_reconnect_attempts", 0),
                    buffer_size=sc_data.get("buffer_size", 2),
                    playback_speed=sc_data.get("playback_speed", 1.0),
                    loop=sc_data.get("loop", False),
                    youtube_quality=sc_data.get("youtube_quality", "best"),
                )

                info = CameraInfo(
                    id=item["id"],
                    name=item["name"],
                    uri=item["uri"],
                    source_type=source_type,
                    username=item.get("username", ""),
                    password=item.get("password", ""),
                    location=item.get("location", ""),
                    group_ids=item.get("group_ids", []),
                    width=item.get("width", 1920),
                    height=item.get("height", 1080),
                    fps=item.get("fps", 30),
                    bitrate_kbps=item.get("bitrate_kbps", 4096),
                    auto_reconnect=item.get("auto_reconnect", True),
                    source_config=source_config,
                    recording_enabled=item.get("recording_enabled", False),
                    ai_enabled=item.get("ai_enabled", False),
                    enabled_features=item.get("enabled_features", []),
                    snapshot_dir=item.get("snapshot_dir", ""),
                    recording_dir=item.get("recording_dir", ""),
                )
                self._cameras[info.id] = info
            self._log.info("Loaded %d cameras from %s", len(self._cameras), self._path)
        except Exception as exc:
            self._log.error("Failed to load cameras: %s", exc)


class InMemoryGroupRepository(GroupRepository):
    """Group repository backed by in-memory dict + JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or Path("groups.json")
        self._groups: dict[str, CameraGroup] = {}
        self._log = LogService.instance()
        self._load()

    def list_all(self) -> Sequence[CameraGroup]:
        return list(self._groups.values())

    def get_by_id(self, group_id: str) -> Optional[CameraGroup]:
        return self._groups.get(group_id)

    def add(self, group: CameraGroup) -> None:
        self._groups[group.id] = group
        self._log.info("Group added: %s (%s)", group.id, group.name)

    def update(self, group: CameraGroup) -> None:
        if group.id in self._groups:
            self._groups[group.id] = group

    def remove(self, group_id: str) -> None:
        self._groups.pop(group_id, None)
        self._log.info("Group removed: %s", group_id)

    def save(self) -> None:
        data = []
        for g in self._groups.values():
            data.append({
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "parent_id": g.parent_id,
                "children_ids": g.children_ids,
                "camera_ids": g.camera_ids,
                "icon": g.icon,
                "color": g.color,
                "is_favorite": g.is_favorite,
                "created_at": g.created_at,
                "updated_at": g.updated_at,
            })
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            self._log.error("Failed to save groups: %s", exc)

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            _VIRTUAL_IDS = {"__all__", "__ungrouped__"}
            for item in data:
                gid = item.get("id", "")
                if gid in _VIRTUAL_IDS:
                    continue
                group = CameraGroup(
                    id=gid,
                    name=item["name"],
                    description=item.get("description", ""),
                    parent_id=item.get("parent_id"),
                    children_ids=item.get("children_ids", []),
                    camera_ids=item.get("camera_ids", []),
                    icon=item.get("icon", ""),
                    color=item.get("color", ""),
                    is_favorite=item.get("is_favorite", False),
                    created_at=item.get("created_at", 0.0),
                    updated_at=item.get("updated_at", 0.0),
                )
                self._groups[group.id] = group
            self._log.info("Loaded %d groups from %s", len(self._groups), self._path)
        except Exception as exc:
            self._log.error("Failed to load groups: %s", exc)
