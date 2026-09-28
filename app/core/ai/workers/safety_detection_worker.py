"""
SafetyDetectionWorker — unified smoke / fire / PPE detection worker.

Runs a single 9-class YOLO model per frame:
    0 person, 1 helmet, 2 vest_coveral, 3 shoes,
    4 no_helmet, 5 no_vest_coveral, 6 no_shoes,
    7 fire, 8 smoke

Trigger logic (per enabled sub-feature):
    - smoke / fire: sustained presence >= 3 s → one event per episode.
    - ppe: a tracked person overlapping a no_* box for >= 3 s →
        one event per person per violation episode. A person can only
        re-trigger after returning to a compliant state.
"""
from __future__ import annotations

import collections
import time
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication, QThread, QObject, Signal, Slot

from app.core.ai.models.model_loader import ModelLoader
from app.core.logging import LogService

_HOLD_SEC = 3.0
_TRACK_IOU = 0.3
_TRACK_MAX_MISS = 30
_PPE_OVERLAP_RATIO = 0.3

_CLS_PERSON = 0
_CLS_NO_HELMET = 4
_CLS_NO_VEST = 5
_CLS_NO_SHOES = 6
_CLS_FIRE = 7
_CLS_SMOKE = 8

_PPE_CLASS_NAMES = {
    _CLS_NO_HELMET: "no_helmet",
    _CLS_NO_VEST: "no_vest_coveral",
    _CLS_NO_SHOES: "no_shoes",
}

_CLS_COLORS = {
    _CLS_FIRE: (0, 0, 255),
    _CLS_SMOKE: (0, 165, 255),
    _CLS_NO_HELMET: (0, 0, 255),
    _CLS_NO_VEST: (0, 0, 255),
    _CLS_NO_SHOES: (0, 0, 255),
}


class _SafetyDetectionWorkerImpl(QObject):
    """Internal worker running YOLO inference in a dedicated QThread.

    Signals:
        annotated_frame_ready(object): FrameData with the annotated BGR frame.
        stopped(): Emitted when the worker finishes processing.
        smoke_alarm(str): camera_id — smoke sustained >= 3 s.
        fire_alarm(str): camera_id — fire sustained >= 3 s.
        ppe_alarm(str, str): camera_id, details — person PPE violation
            sustained >= 3 s.
        smoke_alarm_state(str, bool): camera_id, active.
        fire_alarm_state(str, bool): camera_id, active.
        ppe_alarm_state(str, bool): camera_id, active.
    """

    annotated_frame_ready = Signal(object)
    stopped = Signal()
    frame_submitted = Signal(object)
    smoke_alarm = Signal(str)
    smoke_alarm_state = Signal(str, bool)
    fire_alarm = Signal(str)
    fire_alarm_state = Signal(str, bool)
    ppe_alarm = Signal(str, str)
    ppe_alarm_state = Signal(str, bool)

    def __init__(
        self,
        model_path: str = "app/core/ai/weights/safety/best.pt",
        features: Optional[list[str]] = None,
    ) -> None:
        super().__init__()
        self._log = LogService.instance()
        self._running = True
        self._model = ModelLoader().get_model(model_path)
        self._features: set[str] = set(features or [])

        self._frame_queue: collections.deque = collections.deque(maxlen=1)
        self._fps_counter = 0
        self._fps_timer = time.time()
        self._current_fps = 0.0

        # Sustained-state bookkeeping for smoke / fire.
        self._smoke_since: Optional[float] = None
        self._smoke_triggered = False
        self._smoke_active = False
        self._fire_since: Optional[float] = None
        self._fire_triggered = False
        self._fire_active = False

        # Person tracking (lightweight IoU tracker — per worker instance).
        self._tracks: dict[int, dict] = {}
        self._next_track_id = 0

        # PPE per-person state machine.
        self._ppe_since: dict[int, float] = {}
        self._ppe_triggered: set[int] = set()
        self._ppe_any_active = False

    def set_enabled_features(self, features: list[str]) -> None:
        """Update the set of enabled sub-features at runtime."""
        self._features = set(features)

    def request_stop(self) -> None:
        self._running = False

    @Slot(object)
    def receive_frame(self, frame_data) -> None:
        if not self._running:
            return
        if len(self._frame_queue) >= self._frame_queue.maxlen:
            self._frame_queue.popleft()
        self._frame_queue.append(frame_data)

    def process_frames(self) -> None:
        self._log.info("SafetyDetectionWorker started (%s)", sorted(self._features))
        while self._running:
            QCoreApplication.processEvents()

            if self._frame_queue:
                frame_data = self._frame_queue.popleft()
                annotated = self._run_inference(frame_data)
                self.annotated_frame_ready.emit(annotated)
                self._update_fps()
            else:
                QThread.msleep(1)

        self._log.info("SafetyDetectionWorker stopped")
        self.stopped.emit()

    # ── Inference ──────────────────────────────────────────────────────────

    def _run_inference(self, frame_data):
        now = time.time()
        frame = frame_data.data.copy()
        results = self._model(frame, verbose=False)

        person_boxes: list[tuple[int, int, int, int]] = []
        no_ppe_boxes: list[tuple[int, int, int, int, int]] = []
        fire_boxes: list[tuple[int, int, int, int]] = []
        smoke_boxes: list[tuple[int, int, int, int]] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id = int(box.cls[0])
                if cls_id == _CLS_PERSON:
                    person_boxes.append((x1, y1, x2, y2))
                elif cls_id in _PPE_CLASS_NAMES:
                    no_ppe_boxes.append((cls_id, x1, y1, x2, y2))
                elif cls_id == _CLS_FIRE:
                    fire_boxes.append((x1, y1, x2, y2))
                elif cls_id == _CLS_SMOKE:
                    smoke_boxes.append((x1, y1, x2, y2))

        self._handle_smoke(now, frame_data.camera_id, smoke_boxes)
        self._handle_fire(now, frame_data.camera_id, fire_boxes)

        track_boxes = self._update_tracks(person_boxes)
        self._handle_ppe(now, frame_data.camera_id, track_boxes, no_ppe_boxes)

        self._draw(frame, person_boxes, no_ppe_boxes, fire_boxes, smoke_boxes)

        from app.models import FrameData

        return FrameData(
            camera_id=frame_data.camera_id,
            timestamp=frame_data.timestamp,
            frame_number=frame_data.frame_number,
            width=frame_data.width,
            height=frame_data.height,
            fps=frame_data.fps,
            data=frame,
        )

    # ── Smoke ──────────────────────────────────────────────────────────────

    def _handle_smoke(
        self,
        now: float,
        camera_id: str,
        smoke_boxes: list[tuple[int, int, int, int]],
    ) -> None:
        present = len(smoke_boxes) > 0

        if present:
            if self._smoke_since is None:
                self._smoke_since = now
            if (
                not self._smoke_triggered
                and "smoke_detection" in self._features
                and now - self._smoke_since >= _HOLD_SEC
            ):
                self._smoke_triggered = True
                self.smoke_alarm.emit(camera_id)
        else:
            self._smoke_since = None
            self._smoke_triggered = False

        active = present
        if active != self._smoke_active:
            self._smoke_active = active
            self.smoke_alarm_state.emit(camera_id, active)

    # ── Fire ───────────────────────────────────────────────────────────────

    def _handle_fire(
        self,
        now: float,
        camera_id: str,
        fire_boxes: list[tuple[int, int, int, int]],
    ) -> None:
        present = len(fire_boxes) > 0

        if present:
            if self._fire_since is None:
                self._fire_since = now
            if (
                not self._fire_triggered
                and "fire_detection" in self._features
                and now - self._fire_since >= _HOLD_SEC
            ):
                self._fire_triggered = True
                self.fire_alarm.emit(camera_id)
        else:
            self._fire_since = None
            self._fire_triggered = False

        active = present
        if active != self._fire_active:
            self._fire_active = active
            self.fire_alarm_state.emit(camera_id, active)

    # ── Person tracking ────────────────────────────────────────────────────

    def _update_tracks(
        self, person_boxes: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, tuple[int, int, int, int]]]:
        """Match current person boxes to existing tracks via greedy IoU."""
        current = self._tracks
        new_tracks: dict[int, dict] = {}
        used: set[int] = set()
        visible: list[tuple[int, tuple[int, int, int, int]]] = []

        for box in person_boxes:
            best_id: Optional[int] = None
            best_iou = _TRACK_IOU
            for track_id, t in current.items():
                if track_id in used:
                    continue
                iou = self._boxes_iou(*box, *t["box"])
                if iou > best_iou:
                    best_iou = iou
                    best_id = track_id
            if best_id is not None:
                current[best_id]["box"] = box
                current[best_id]["miss"] = 0
                new_tracks[best_id] = current[best_id]
                used.add(best_id)
                visible.append((best_id, box))
            else:
                self._next_track_id += 1
                new_tracks[self._next_track_id] = {
                    "box": box,
                    "miss": 0,
                }
                used.add(self._next_track_id)
                visible.append((self._next_track_id, box))

        for track_id, t in current.items():
            if track_id in used:
                continue
            t["miss"] += 1
            if t["miss"] <= _TRACK_MAX_MISS:
                new_tracks[track_id] = t

        self._tracks = new_tracks
        return visible

    # ── PPE ────────────────────────────────────────────────────────────────

    def _handle_ppe(
        self,
        now: float,
        camera_id: str,
        track_boxes: list[tuple[int, tuple[int, int, int, int]]],
        no_ppe_boxes: list[tuple[int, int, int, int, int]],
    ) -> None:
        any_active = False

        for track_id, (px1, py1, px2, py2) in track_boxes:
            violations = [
                _PPE_CLASS_NAMES[cls_id]
                for cls_id, nx1, ny1, nx2, ny2 in no_ppe_boxes
                if self._ppe_overlap(nx1, ny1, nx2, ny2, px1, py1, px2, py2)
            ]

            if violations:
                any_active = True
                if track_id not in self._ppe_triggered:
                    if track_id not in self._ppe_since:
                        self._ppe_since[track_id] = now
                    elif (
                        "ppe_detection" in self._features
                        and now - self._ppe_since[track_id] >= _HOLD_SEC
                    ):
                        self._ppe_triggered.add(track_id)
                        self._ppe_since.pop(track_id, None)
                        detail = f"person {track_id}: {', '.join(violations)}"
                        self.ppe_alarm.emit(camera_id, detail)
            else:
                self._ppe_since.pop(track_id, None)
                self._ppe_triggered.discard(track_id)

        if any_active != self._ppe_any_active:
            self._ppe_any_active = any_active
            self.ppe_alarm_state.emit(camera_id, any_active)

    # ── Drawing ────────────────────────────────────────────────────────────

    def _draw(
        self,
        frame: np.ndarray,
        person_boxes: list[tuple[int, int, int, int]],
        no_ppe_boxes: list[tuple[int, int, int, int, int]],
        fire_boxes: list[tuple[int, int, int, int]],
        smoke_boxes: list[tuple[int, int, int, int]],
    ) -> None:
        if "fire_detection" in self._features:
            for x1, y1, x2, y2 in fire_boxes:
                self._draw_detection(frame, x1, y1, x2, y2, _CLS_COLORS[_CLS_FIRE])
        if "smoke_detection" in self._features:
            for x1, y1, x2, y2 in smoke_boxes:
                self._draw_detection(frame, x1, y1, x2, y2, _CLS_COLORS[_CLS_SMOKE])
        if "ppe_detection" in self._features:
            for px1, py1, px2, py2 in person_boxes:
                violating = any(
                    self._ppe_overlap(nx1, ny1, nx2, ny2, px1, py1, px2, py2)
                    for cls_id, nx1, ny1, nx2, ny2 in no_ppe_boxes
                )
                color = (0, 0, 255) if violating else (0, 255, 0)
                self._draw_detection(frame, px1, py1, px2, py2, color)

    @staticmethod
    def _draw_detection(
        frame: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int] = (0, 255, 0),
    ) -> None:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    @staticmethod
    def _boxes_iou(
        ax1: int, ay1: int, ax2: int, ay2: int,
        bx1: int, by1: int, bx2: int, by2: int,
    ) -> float:
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        a_area = (ax2 - ax1) * (ay2 - ay1)
        b_area = (bx2 - bx1) * (by2 - by1)
        union = a_area + b_area - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _ppe_overlap(
        ax1: int, ay1: int, ax2: int, ay2: int,
        bx1: int, by1: int, bx2: int, by2: int,
    ) -> bool:
        """True if the small (no-PPE) box mostly lies inside the large (person) box.

        Uses the ratio of intersection area to the smaller box's area, because
        IoU between a small PPE item and a large person box is naturally tiny.
        """
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return False
        inter = (ix2 - ix1) * (iy2 - iy1)
        small_area = min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))
        if small_area <= 0:
            return False
        return inter / small_area >= _PPE_OVERLAP_RATIO

    # ── FPS tracking ───────────────────────────────────────────────────────

    def _update_fps(self) -> None:
        self._fps_counter += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._current_fps = self._fps_counter / elapsed
            self._fps_counter = 0
            self._fps_timer = time.time()


class SafetyDetectionWorker(QObject):
    """Public façade that manages the internal worker + QThread pair."""

    annotated_frame_ready = Signal(object)
    smoke_alarm = Signal(str)
    smoke_alarm_state = Signal(str, bool)
    fire_alarm = Signal(str)
    fire_alarm_state = Signal(str, bool)
    ppe_alarm = Signal(str, str)
    ppe_alarm_state = Signal(str, bool)

    def __init__(
        self,
        model_path: str = "app/core/ai/weights/safety/best.pt",
        features: Optional[list[str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._log = LogService.instance()
        self._thread: Optional[QThread] = None
        self._impl: Optional[_SafetyDetectionWorkerImpl] = None
        self._model_path = model_path
        self._features = list(features or [])

    def start(self) -> None:
        if self._thread is not None:
            return

        self._thread = QThread()
        self._impl = _SafetyDetectionWorkerImpl(self._model_path, self._features)
        self._impl.moveToThread(self._thread)

        self._thread.started.connect(self._impl.process_frames)
        self._impl.stopped.connect(self._thread.quit)
        self._impl.stopped.connect(self._impl.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._impl.annotated_frame_ready.connect(self.annotated_frame_ready)
        self._impl.smoke_alarm.connect(self.smoke_alarm)
        self._impl.smoke_alarm_state.connect(self.smoke_alarm_state)
        self._impl.fire_alarm.connect(self.fire_alarm)
        self._impl.fire_alarm_state.connect(self.fire_alarm_state)
        self._impl.ppe_alarm.connect(self.ppe_alarm)
        self._impl.ppe_alarm_state.connect(self.ppe_alarm_state)
        self._impl.frame_submitted.connect(self._impl.receive_frame)

        self._log.info("Starting SafetyDetectionWorker thread")
        self._thread.start()

    def set_enabled_features(self, features: list[str]) -> None:
        self._features = list(features)
        if self._impl is not None:
            self._impl.set_enabled_features(features)

    def stop(self) -> None:
        if self._impl is not None:
            self._impl.request_stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(5000):
                self._log.warning("SafetyDetectionWorker thread did not finish in 5s")
        self._impl = None
        self._thread = None
        self._log.info("SafetyDetectionWorker stopped")

    def submit_frame(self, frame_data) -> None:
        if self._impl is not None:
            self._impl.frame_submitted.emit(frame_data)
