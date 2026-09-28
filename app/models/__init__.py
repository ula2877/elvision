"""
Core types used across all layers of the application.
"""
from __future__ import annotations

import enum
import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Enums ──────────────────────────────────────────────────────────────────────


class SourceType(enum.Enum):
    """All supported video source types."""

    WEBCAM = "webcam"
    VIDEO_FILE = "video_file"
    RTSP = "rtsp"
    HLS = "hls"
    YOUTUBE = "youtube"
    NETWORK_STREAM = "network_stream"
    IP_CAMERA = "ip_camera"
    ONVIF = "onvif"
    ORBBEC = "orbbec"
    BASLER = "basler"
    HIKROBOT = "hikrobot"
    GIGE = "gige"
    SRT = "srt"
    RTMP = "rtmp"
    NDI = "ndi"

    @property
    def display_name(self) -> str:
        return self.value.upper().replace("_", " ")


class TransportProtocol(enum.Enum):
    TCP = "tcp"
    UDP = "udp"
    AUTO = "auto"


class CameraStatus(enum.Enum):
    """UI-facing status. CameraWidget displays this."""

    CONNECTING = "connecting"
    ONLINE = "online"
    OFFLINE = "offline"
    BUFFERING = "buffering"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PAUSED = "paused"


class CameraState(enum.Enum):
    """Internal camera state machine.

    Transitions:
        IDLE → CONNECTING → CONNECTED → STREAMING
        STREAMING → BUFFERING → RECONNECTING → CONNECTING
        STREAMING → DISCONNECTED → ERROR
        Any → STOPPING → STOPPED
        Any → ERROR
    """

    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    BUFFERING = "buffering"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


_VALID_TRANSITIONS: dict[CameraState, set[CameraState]] = {
    CameraState.IDLE: {CameraState.CONNECTING, CameraState.STOPPING, CameraState.ERROR},
    CameraState.CONNECTING: {
        CameraState.CONNECTED,
        CameraState.ERROR,
        CameraState.STOPPING,
        CameraState.DISCONNECTED,
    },
    CameraState.CONNECTED: {
        CameraState.STREAMING,
        CameraState.BUFFERING,
        CameraState.ERROR,
        CameraState.STOPPING,
        CameraState.DISCONNECTED,
    },
    CameraState.STREAMING: {
        CameraState.BUFFERING,
        CameraState.DISCONNECTED,
        CameraState.ERROR,
        CameraState.STOPPING,
        CameraState.CONNECTED,
    },
    CameraState.BUFFERING: {
        CameraState.RECONNECTING,
        CameraState.STREAMING,
        CameraState.ERROR,
        CameraState.STOPPING,
        CameraState.DISCONNECTED,
    },
    CameraState.RECONNECTING: {
        CameraState.CONNECTING,
        CameraState.ERROR,
        CameraState.STOPPING,
    },
    CameraState.DISCONNECTED: {
        CameraState.CONNECTING,
        CameraState.ERROR,
        CameraState.STOPPING,
    },
    CameraState.STOPPING: {CameraState.STOPPED},
    CameraState.STOPPED: {CameraState.IDLE, CameraState.CONNECTING},
    CameraState.ERROR: {CameraState.IDLE, CameraState.CONNECTING, CameraState.STOPPING},
}


def is_valid_transition(from_state: CameraState, to_state: CameraState) -> bool:
    """Check if a state transition is valid."""
    allowed = _VALID_TRANSITIONS.get(from_state)
    if allowed is None:
        return False
    return to_state in allowed


def camera_state_to_status(state: CameraState) -> CameraStatus:
    """Map internal CameraState → UI-facing CameraStatus."""
    _MAP = {
        CameraState.IDLE: CameraStatus.OFFLINE,
        CameraState.CONNECTING: CameraStatus.CONNECTING,
        CameraState.CONNECTED: CameraStatus.CONNECTING,
        CameraState.STREAMING: CameraStatus.ONLINE,
        CameraState.BUFFERING: CameraStatus.BUFFERING,
        CameraState.RECONNECTING: CameraStatus.BUFFERING,
        CameraState.DISCONNECTED: CameraStatus.DISCONNECTED,
        CameraState.STOPPING: CameraStatus.OFFLINE,
        CameraState.STOPPED: CameraStatus.OFFLINE,
        CameraState.ERROR: CameraStatus.ERROR,
    }
    return _MAP.get(state, CameraStatus.OFFLINE)


class RecordingMode(enum.Enum):
    CONTINUOUS = "continuous"
    MOTION = "motion"
    AI_TRIGGER = "ai_trigger"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class LayoutGrid(enum.Enum):
    GRID_1X1 = (1, 1)
    GRID_2X2 = (2, 2)
    GRID_3X3 = (3, 3)
    GRID_4X4 = (4, 4)
    GRID_5X5 = (5, 5)
    GRID_6X6 = (6, 6)
    GRID_7X7 = (7, 7)
    GRID_8X8 = (8, 8)
    CUSTOM = (0, 0)

    @property
    def rows(self) -> int:
        return self.value[0]

    @property
    def cols(self) -> int:
        return self.value[1]

    @property
    def capacity(self) -> int:
        return self.rows * self.cols


class DisplayMode(enum.Enum):
    """Video display mode inside a camera cell.

    FIT   — Entire frame visible, aspect ratio preserved, letterboxed.
    FILL  — Fill cell, aspect ratio preserved, excess cropped.
    STRETCH — Fill cell, aspect ratio ignored, no borders.
    """

    FIT = "fit"
    FILL = "fill"
    STRETCH = "stretch"


class LogLevel(enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ThemeMode(enum.Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


# ── Source Capability Metadata ────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceCapabilities:
    """Describes what a source type supports."""

    can_pause: bool = False
    can_seek: bool = False
    can_loop: bool = False
    can_set_speed: bool = False
    can_reconnect: bool = True
    requires_network: bool = False
    requires_auth: bool = False
    supports_transport_protocol: bool = False


_SOURCE_CAPABILITIES: dict[SourceType, SourceCapabilities] = {
    SourceType.WEBCAM: SourceCapabilities(can_reconnect=True),
    SourceType.VIDEO_FILE: SourceCapabilities(
        can_pause=True, can_seek=True, can_loop=True, can_set_speed=True
    ),
    SourceType.RTSP: SourceCapabilities(
        requires_network=True,
        requires_auth=True,
        supports_transport_protocol=True,
    ),
    SourceType.HLS: SourceCapabilities(requires_network=True),
    SourceType.YOUTUBE: SourceCapabilities(requires_network=True),
    SourceType.NETWORK_STREAM: SourceCapabilities(requires_network=True),
    SourceType.IP_CAMERA: SourceCapabilities(
        requires_network=True,
        requires_auth=True,
        supports_transport_protocol=True,
    ),
    SourceType.ONVIF: SourceCapabilities(requires_network=True, requires_auth=True),
    SourceType.ORBBEC: SourceCapabilities(can_reconnect=False),
    SourceType.BASLER: SourceCapabilities(can_reconnect=False),
    SourceType.HIKROBOT: SourceCapabilities(can_reconnect=False),
    SourceType.GIGE: SourceCapabilities(can_reconnect=False),
    SourceType.SRT: SourceCapabilities(requires_network=True),
    SourceType.RTMP: SourceCapabilities(requires_network=True),
    SourceType.NDI: SourceCapabilities(requires_network=True),
}


def get_source_capabilities(source_type: SourceType) -> SourceCapabilities:
    return _SOURCE_CAPABILITIES.get(source_type, SourceCapabilities())


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class SourceConfig:
    """Transport-specific connection parameters."""

    transport_protocol: TransportProtocol = TransportProtocol.AUTO
    connection_timeout_sec: float = 10.0
    reconnect_interval_sec: float = 5.0
    max_reconnect_attempts: int = 0  # 0 = infinite
    buffer_size: int = 2
    rtsp_transport: str = "tcp"
    seek_position_sec: float = 0.0
    playback_speed: float = 1.0
    loop: bool = False
    youtube_quality: str = "best"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CameraInfo:
    """Full descriptor for a camera source."""

    id: str
    name: str
    uri: str
    source_type: SourceType = SourceType.RTSP
    username: str = ""
    password: str = ""
    location: str = ""
    group_ids: list[str] = field(default_factory=list)
    width: int = 1920
    height: int = 1080
    fps: int = 30
    bitrate_kbps: int = 4096
    auto_reconnect: bool = True
    source_config: SourceConfig = field(default_factory=SourceConfig)
    recording_enabled: bool = False
    ai_enabled: bool = False
    enabled_features: list[str] = field(default_factory=list)
    snapshot_dir: str = ""
    recording_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceMetadata:
    """Runtime metadata returned by a source after opening."""

    codec: str = ""
    native_width: int = 0
    native_height: int = 0
    native_fps: float = 0.0
    fourcc: str = ""
    total_frames: int = 0
    duration_sec: float = 0.0
    bitrate: int = 0
    is_seekable: bool = False
    is_network_stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameData:
    """Single decoded video frame with metadata."""

    camera_id: str
    timestamp: float
    frame_number: int
    width: int
    height: int
    fps: float
    data: Any  # numpy.ndarray

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height > 0 else 0.0


@dataclass
class ConnectionStats:
    """Health & performance metrics for a single stream."""

    camera_id: str
    status: CameraStatus = CameraStatus.OFFLINE
    fps_current: float = 0.0
    fps_target: int = 30
    bandwidth_kbps: float = 0.0
    dropped_frames: int = 0
    uptime_seconds: float = 0.0
    reconnect_attempts: int = 0
    last_error: str = ""
    signal_strength: int = 100
    latency_ms: float = 0.0


@dataclass
class CameraGroup:
    """Hierarchical grouping node.

    Designed for enterprise Elvision scalability:
      - parent_id / children_ids support nested groups (Buildings → Floors → Sites)
      - camera_ids holds direct membership
      - is_favorite flags quick-access groups
      - metadata allows future extension (permissions, smart rules, etc.)
    """

    id: str
    name: str
    description: str = ""
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    camera_ids: list[str] = field(default_factory=list)
    icon: str = ""
    color: str = ""
    is_favorite: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordingJob:
    """Immutable recording request."""

    camera_id: str
    mode: RecordingMode = RecordingMode.CONTINUOUS
    output_path: str = ""
    max_duration_sec: int = 300
    max_file_size_mb: int = 1024
    motion_sensitivity: int = 50
    schedule: str = ""


@dataclass
class SnapshotRequest:
    """Immutable snapshot request."""

    camera_id: str
    output_path: str = ""
    format: str = "jpg"
    quality: int = 95
    timestamp: bool = True


@dataclass
class AppConfig:
    """Application-wide configuration."""

    theme: ThemeMode = ThemeMode.DARK
    language: str = "en"
    max_cameras: int = 64
    default_layout: str = "GRID_1X1"
    log_level: LogLevel = LogLevel.INFO
    enable_gpu: bool = False
    hardware_accel: str = ""
    frame_buffer_size: int = 30
    reconnect_interval_sec: float = 5.0
    health_check_interval_sec: float = 10.0
    enable_virtual_rendering: bool = True
    hidden_camera_fps: int = 5
    plugins_enabled: bool = True
    plugins_path: str = "plugins"


# ── Backward compatibility alias ──────────────────────────────────────────────

# Deprecated: use SourceType instead
CameraTransport = SourceType  # type: ignore[misc]
