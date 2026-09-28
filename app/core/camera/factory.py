"""
VideoSourceFactory — creates VideoSource instances from SourceType.
New sources are registered at module level. No other code changes required.
"""
from __future__ import annotations

import logging
from typing import Callable

from app.core.camera.base import VideoSource
from app.core.logging import LogService
from app.models import CameraInfo, SourceType


logger = logging.getLogger(__name__)

_REGISTRY: dict[SourceType, Callable[[CameraInfo], VideoSource]] = {}


def register_source(source_type: SourceType, factory_fn: Callable[[CameraInfo], VideoSource]) -> None:
    """Register a factory function for a source type."""
    _REGISTRY[source_type] = factory_fn


class VideoSourceFactory:
    """Creates VideoSource instances from CameraInfo.
    Follows OCP: add new sources by calling register_source().
    """

    @staticmethod
    def create(info: CameraInfo) -> VideoSource:
        """Create the correct VideoSource for the given CameraInfo."""
        factory_fn = _REGISTRY.get(info.source_type)
        if factory_fn is None:
            log = LogService.instance()
            log.error("No registered source for type: %s", info.source_type)
            msg = f"Unsupported source type: {info.source_type.value}"
            raise ValueError(msg)

        return factory_fn(info)

    @staticmethod
    def supported_types() -> list[SourceType]:
        """Return all registered source types."""
        return list(_REGISTRY.keys())

    @staticmethod
    def is_supported(source_type: SourceType) -> bool:
        return source_type in _REGISTRY


# ── Register built-in sources ──────────────────────────────────────────────────
# Imported lazily to avoid circular imports at module load time.
# The registration runs when this module is first imported.


def _register_builtin_sources() -> None:
    from app.core.camera.sources.webcam import WebcamSource
    from app.core.camera.sources.video_file import VideoFileSource
    from app.core.camera.sources.rtsp import RTSPSource
    from app.core.camera.sources.hls import HLSStreamSource
    from app.core.camera.sources.youtube import YoutubeSource
    from app.core.camera.sources.network import NetworkStreamSource

    register_source(SourceType.WEBCAM, WebcamSource)
    register_source(SourceType.VIDEO_FILE, VideoFileSource)
    register_source(SourceType.RTSP, RTSPSource)
    register_source(SourceType.IP_CAMERA, RTSPSource)
    register_source(SourceType.HLS, HLSStreamSource)
    register_source(SourceType.YOUTUBE, YoutubeSource)
    register_source(SourceType.NETWORK_STREAM, NetworkStreamSource)

    logger.info(
        "Registered %d source types: %s",
        len(_REGISTRY),
        [st.value for st in _REGISTRY],
    )


_register_builtin_sources()
