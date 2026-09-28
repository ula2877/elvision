from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from app.core.ai.registry import AIFeatureRegistry
from app.core.ai.workers.fall_detection_worker import FallDetectionWorker
from app.core.ai.workers.safety_detection_worker import SafetyDetectionWorker
from app.core.logging import LogService
from app.models import CameraInfo

if TYPE_CHECKING:
    from app.core.camera.registry import CameraRegistry
    from app.ui.workspace.workspace import Workspace


_FEATURE_WORKER_MAP: dict[str, tuple[type, dict]] = {
    "fall_detection": (
        FallDetectionWorker,
        {"model_path": "app/core/ai/weights/fall_detection/best.pt"},
    ),
}

_SAFETY_WORKER_KEY = "safety_detection"
_SAFETY_FEATURES = ("smoke_detection", "fire_detection", "ppe_detection")
_SAFETY_MODEL_PATH = "app/core/ai/weights/safety/best.pt"


_WORKER_SIGNALS = (
    "fall_alarm",
    "fall_alarm_state",
    "smoke_alarm",
    "smoke_alarm_state",
    "fire_alarm",
    "fire_alarm_state",
    "ppe_alarm",
    "ppe_alarm_state",
)


class AIFeatureManager(QObject):
    annotated_frame_ready = Signal(object)
    fall_alarm = Signal(str)
    fall_alarm_state = Signal(str, bool)
    smoke_alarm = Signal(str)
    smoke_alarm_state = Signal(str, bool)
    fire_alarm = Signal(str)
    fire_alarm_state = Signal(str, bool)
    ppe_alarm = Signal(str, str)
    ppe_alarm_state = Signal(str, bool)

    def __init__(
        self,
        camera_registry: CameraRegistry,
        workspace: Workspace,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._log = LogService.instance()
        self._camera_registry = camera_registry
        self._workspace = workspace

        # camera_id -> {feature_key: worker}
        self._workers: dict[str, dict[str, object]] = {}

    # ── Frame routing ──────────────────────────────────────────────────────

    def process_frame(self, frame_data) -> None:
        camera_id = frame_data.camera_id
        entry = self._camera_registry.get(camera_id)
        if entry is None:
            self._forward_frame(frame_data)
            return

        workers = self._workers.get(camera_id, {})
        if not workers:
            self._forward_frame(frame_data)
            return

        for worker in workers.values():
            worker.submit_frame(frame_data)

    # ── Camera lifecycle ───────────────────────────────────────────────────

    def start_camera(self, info: CameraInfo) -> None:
        camera_id = info.id

        if camera_id in self._workers:
            self._log.warning(
                "AI workers already exist for %s — skipping", camera_id
            )
            return

        enabled = set(info.enabled_features)
        new_workers: dict[str, object] = {}

        for feature_key, (cls, kwargs) in _FEATURE_WORKER_MAP.items():
            if feature_key not in enabled:
                continue
            worker = self._build_worker(feature_key, cls, kwargs)
            if worker is not None:
                new_workers[feature_key] = worker
                self._log.info("Started %s for %s", cls.__name__, camera_id)

        safety_enabled = sorted(set(_SAFETY_FEATURES) & enabled)
        if safety_enabled:
            worker = self._build_safety_worker(safety_enabled)
            if worker is not None:
                new_workers[_SAFETY_WORKER_KEY] = worker
                self._log.info(
                    "Started %s for %s (features=%s)",
                    type(worker).__name__,
                    camera_id,
                    safety_enabled,
                )

        if new_workers:
            self._workers[camera_id] = new_workers

    def stop_camera(self, camera_id: str) -> None:
        workers = self._workers.pop(camera_id, {})
        for feature_key, worker in workers.items():
            self._destroy_worker(worker, feature_key)
        if workers:
            self._log.info(
                "Stopped %d AI worker(s) for %s", len(workers), camera_id
            )

    def stop_all(self) -> None:
        for camera_id in list(self._workers.keys()):
            self.stop_camera(camera_id)

    def update_camera_features(self, info: CameraInfo) -> None:
        camera_id = info.id
        current_keys = set(info.enabled_features)
        running = self._workers.get(camera_id, {})
        running_keys = set(running.keys())

        to_start = current_keys & _FEATURE_WORKER_MAP.keys() - running_keys
        to_stop = running_keys & _FEATURE_WORKER_MAP.keys() - current_keys

        for feature_key in to_start:
            cls, kwargs = _FEATURE_WORKER_MAP[feature_key]
            worker = self._build_worker(feature_key, cls, kwargs)
            if worker is not None:
                running[feature_key] = worker
                self._log.info("Started %s for %s (toggled on)", cls.__name__, camera_id)

        for feature_key in to_stop:
            worker = running.pop(feature_key, None)
            if worker is not None:
                self._destroy_worker(worker, feature_key)
                self._log.info(
                    "Stopped worker for %s on %s (toggled off)", feature_key, camera_id
                )

        safety_enabled = sorted(set(_SAFETY_FEATURES) & current_keys)
        safety_running = _SAFETY_WORKER_KEY in running_keys
        if safety_enabled and not safety_running:
            worker = self._build_safety_worker(safety_enabled)
            if worker is not None:
                running[_SAFETY_WORKER_KEY] = worker
                self._log.info(
                    "Started safety worker for %s (toggled on)", camera_id
                )
        elif not safety_enabled and safety_running:
            worker = running.pop(_SAFETY_WORKER_KEY, None)
            if worker is not None:
                self._destroy_worker(worker, _SAFETY_WORKER_KEY)
                self._log.info(
                    "Stopped safety worker on %s (toggled off)", camera_id
                )
        elif safety_enabled and safety_running:
            set_enabled = getattr(running[_SAFETY_WORKER_KEY], "set_enabled_features", None)
            if set_enabled is not None:
                set_enabled(safety_enabled)

        if running and not self._workers.get(camera_id):
            self._workers[camera_id] = running
        elif not running:
            self._workers.pop(camera_id, None)

    # ── Worker factory ────────────────────────────────────────────────────

    def _build_safety_worker(self, features: list[str]) -> Optional[object]:
        try:
            worker = SafetyDetectionWorker(
                model_path=_SAFETY_MODEL_PATH, features=features
            )
            worker.annotated_frame_ready.connect(self._on_annotated_frame)
            for signal_name in ("smoke_alarm", "smoke_alarm_state"):
                sig = getattr(worker, signal_name, None)
                if sig is not None:
                    sig.connect(getattr(self, signal_name))
            for signal_name in ("fire_alarm", "fire_alarm_state"):
                sig = getattr(worker, signal_name, None)
                if sig is not None:
                    sig.connect(getattr(self, signal_name))
            for signal_name in ("ppe_alarm", "ppe_alarm_state"):
                sig = getattr(worker, signal_name, None)
                if sig is not None:
                    sig.connect(getattr(self, signal_name))
            worker.start()
            return worker
        except Exception as exc:
            self._log.error(
                "Failed to build safety worker for %s: %s", features, exc
            )
            return None

    def _build_worker(self, feature_key: str, cls: type, kwargs: dict) -> Optional[object]:
        try:
            worker = cls(**kwargs)
            worker.annotated_frame_ready.connect(self._on_annotated_frame)
            for signal_name in _WORKER_SIGNALS:
                sig = getattr(worker, signal_name, None)
                if sig is not None:
                    sig.connect(getattr(self, signal_name))
            worker.start()
            return worker
        except Exception as exc:
            self._log.error(
                "Failed to build worker %s for %s: %s", cls.__name__, feature_key, exc
            )
            return None

    def _destroy_worker(self, worker: object, feature_key: str) -> None:
        try:
            worker.annotated_frame_ready.disconnect(self._on_annotated_frame)
        except (RuntimeError, TypeError):
            pass
        for signal_name in _WORKER_SIGNALS:
            sig = getattr(worker, signal_name, None)
            if sig is not None:
                try:
                    sig.disconnect(getattr(self, signal_name))
                except (RuntimeError, TypeError):
                    pass
        worker.stop()

    # ── Internal ───────────────────────────────────────────────────────────

    def _on_annotated_frame(self, frame_data) -> None:
        self.annotated_frame_ready.emit(frame_data)
        self._forward_frame(frame_data)

    def _forward_frame(self, frame_data) -> None:
        self._workspace.feed_frame(frame_data)
