from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


EVENT_TYPE_FALL = "fall_detection"
EVENT_TYPE_SMOKE = "smoke"
EVENT_TYPE_FIRE = "fire"
EVENT_TYPE_PPE = "ppe"
EVENT_TYPE_RESTRICTED_AREA = "restricted_area"
EVENT_TYPE_INTRUSION = "intrusion"
EVENT_TYPE_LOITERING = "loitering"
EVENT_TYPE_VEHICLE = "vehicle"
EVENT_TYPE_FACE = "face"
EVENT_TYPE_CAMERA_OFFLINE = "camera_offline"
EVENT_TYPE_RECORDING = "recording"


EVENT_STATUS_NEW = "new"
EVENT_STATUS_ACKNOWLEDGED = "acknowledged"
EVENT_STATUS_RESOLVED = "resolved"
EVENT_STATUS_DISMISSED = "dismissed"


EVENT_STATUS_ACTIVE = [EVENT_STATUS_NEW]
EVENT_STATUS_ALL = [
    EVENT_STATUS_NEW,
    EVENT_STATUS_ACKNOWLEDGED,
    EVENT_STATUS_RESOLVED,
    EVENT_STATUS_DISMISSED,
]

EVENT_TYPES_ALL = [
    EVENT_TYPE_FALL,
    EVENT_TYPE_SMOKE,
    EVENT_TYPE_FIRE,
    EVENT_TYPE_PPE,
    EVENT_TYPE_RESTRICTED_AREA,
    EVENT_TYPE_INTRUSION,
    EVENT_TYPE_LOITERING,
    EVENT_TYPE_VEHICLE,
    EVENT_TYPE_FACE,
    EVENT_TYPE_CAMERA_OFFLINE,
    EVENT_TYPE_RECORDING,
]

EVENT_TYPE_LABELS: dict[str, str] = {
    EVENT_TYPE_FALL: "Fall Detection",
    EVENT_TYPE_SMOKE: "Smoke Detected",
    EVENT_TYPE_FIRE: "Fire Detected",
    EVENT_TYPE_PPE: "PPE Violation",
    EVENT_TYPE_RESTRICTED_AREA: "Restricted Area",
    EVENT_TYPE_INTRUSION: "Intrusion",
    EVENT_TYPE_LOITERING: "Loitering",
    EVENT_TYPE_VEHICLE: "Vehicle",
    EVENT_TYPE_FACE: "Face",
    EVENT_TYPE_CAMERA_OFFLINE: "Camera Offline",
    EVENT_TYPE_RECORDING: "Recording",
}

EVENT_TYPE_COLORS: dict[str, str] = {
    EVENT_TYPE_FALL: "#DC2626",
    EVENT_TYPE_SMOKE: "#F97316",
    EVENT_TYPE_FIRE: "#EF4444",
    EVENT_TYPE_PPE: "#8B5CF6",
    EVENT_TYPE_RESTRICTED_AREA: "#F59E0B",
    EVENT_TYPE_INTRUSION: "#DC2626",
    EVENT_TYPE_LOITERING: "#F59E0B",
    EVENT_TYPE_VEHICLE: "#3B82F6",
    EVENT_TYPE_FACE: "#8B5CF6",
    EVENT_TYPE_CAMERA_OFFLINE: "#6B7280",
    EVENT_TYPE_RECORDING: "#10B981",
}

EVENT_TYPE_ICONS: dict[str, str] = {
    EVENT_TYPE_FALL: "\u26a0",
    EVENT_TYPE_SMOKE: "\ud83d\udd25",
    EVENT_TYPE_FIRE: "\ud83d\udd25",
    EVENT_TYPE_PPE: "\ud83d\udee1\ufe0f",
    EVENT_TYPE_RESTRICTED_AREA: "\ud83d\udea8",
    EVENT_TYPE_INTRUSION: "\ud83d\udea8",
    EVENT_TYPE_LOITERING: "\u26a0",
    EVENT_TYPE_VEHICLE: "\ud83d\ude97",
    EVENT_TYPE_FACE: "\ud83d\udc64",
    EVENT_TYPE_CAMERA_OFFLINE: "\u26a0",
    EVENT_TYPE_RECORDING: "\u23fa",
}


@dataclass
class EventRecord:
    id: int = 0
    timestamp: float = 0.0
    camera_id: str = ""
    camera_name: str = ""
    group_name: str = ""
    event_type: str = EVENT_TYPE_FALL
    confidence: float = 0.0
    snapshot_path: str = ""
    status: str = EVENT_STATUS_NEW
    notes: str = ""

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    @property
    def event_label(self) -> str:
        return EVENT_TYPE_LABELS.get(self.event_type, self.event_type)

    @property
    def event_color(self) -> str:
        return EVENT_TYPE_COLORS.get(self.event_type, "#6B7280")

    @property
    def event_icon(self) -> str:
        return EVENT_TYPE_ICONS.get(self.event_type, "\u26a0")


@dataclass
class EventFilter:
    search: str = ""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    camera_id: Optional[str] = None
    group_name: Optional[str] = None
    event_type: Optional[str] = None
    status: Optional[str] = None
