"""
FallDetectionWorker — dedicated AI inference worker for fall detection.

Responsibilities:
    - Load a pretrained YOLO model once via ModelLoader.
    - Receive raw BGR frames from CameraWorker (via FeatureManager).
    - Run YOLO object detection inference.
    - Draw bounding boxes, class names, and confidence scores.
    - Return the annotated frame.

This worker does NOT perform fall classification, pose estimation,
tracking, or any business logic.  It only runs standard COCO object
detection and visualises the results.
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


_ALARM_HOLD_SEC = 3.0


class _FallDetectionWorkerImpl(QObject):
    """Internal worker that runs YOLO inference in a dedicated QThread.

    Signals:
        annotated_frame_ready(object): Emitted with FrameData containing
            the annotated BGR numpy array in ``data``.
        stopped(): Emitted when the worker has finished processing and
            is shutting down.
    """

    annotated_frame_ready = Signal(object)  # FrameData
    stopped = Signal()
    frame_submitted = Signal(object)  # FrameData — cross-thread submission
    fall_alarm = Signal(str)  # camera_id — emitted when alarm activates
    fall_alarm_state = Signal(str, bool)  # camera_id, active

    def __init__(self, model_path: str = "app/core/ai/weights/fall_detection/best.pt") -> None:
        super().__init__()
        self._log = LogService.instance()
        self._running = True
        self._model = ModelLoader().get_model(model_path)

        self._frame_queue: collections.deque = collections.deque(maxlen=1)
        self._fps_counter = 0
        self._fps_timer = time.time()
        self._current_fps = 0.0
        self._alarmed_boxes: list[tuple[float, int, int, int, int]] = []
        self._previous_alarmed: bool = False

    def request_stop(self) -> None:
        """Thread-safe stop request."""
        self._running = False

    @Slot(object)
    def receive_frame(self, frame_data) -> None:
        """Enqueue a frame for processing. Keeps only the latest frame."""
        if not self._running:
            return
        if len(self._frame_queue) >= self._frame_queue.maxlen:
            self._frame_queue.popleft()
        self._frame_queue.append(frame_data)

    def process_frames(self) -> None:
        """Main processing loop. Runs in the worker QThread.

        Pulls the latest frame from the queue, runs YOLO inference,
        draws detection boxes, and emits the annotated frame.
        """
        self._log.info("FallDetectionWorker started")
        while self._running:
            QCoreApplication.processEvents()

            if self._frame_queue:
                frame_data = self._frame_queue.popleft()
                annotated = self._run_inference(frame_data)
                self.annotated_frame_ready.emit(annotated)
                self._update_fps()
            else:
                QThread.msleep(1)

        self._log.info("FallDetectionWorker stopped")
        self.stopped.emit()

    # ── Inference ──────────────────────────────────────────────────────────

    def _run_inference(self, frame_data):
        """Run YOLO detection and return a new FrameData with annotated frame."""
        now = time.time()
        frame = frame_data.data.copy()
        results = self._model(frame, verbose=False)

        person_boxes: list[tuple[int, int, int, int]] = []
        fall_boxes: list[tuple[int, int, int, int]] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id = int(box.cls[0])
                label = result.names.get(cls_id, str(cls_id))

                if label == "person":
                    person_boxes.append((x1, y1, x2, y2))
                elif label == "fall":
                    fall_boxes.append((x1, y1, x2, y2))

        self._alarmed_boxes = [
            e for e in self._alarmed_boxes if now - e[0] < _ALARM_HOLD_SEC
        ]

        alarmed_person_indices: set[int] = set()

        for i, pb in enumerate(person_boxes):
            px1, py1, px2, py2 = pb
            for fx1, fy1, fx2, fy2 in fall_boxes:
                if self._boxes_iou(fx1, fy1, fx2, fy2, px1, py1, px2, py2) > 0.8:
                    alarmed_person_indices.add(i)
                    self._alarmed_boxes.append((now, *pb))
                    break

        for i, pb in enumerate(person_boxes):
            if i in alarmed_person_indices:
                continue
            for ts, rx1, ry1, rx2, ry2 in self._alarmed_boxes:
                if self._boxes_iou(pb[0], pb[1], pb[2], pb[3], rx1, ry1, rx2, ry2) > 0.8:
                    alarmed_person_indices.add(i)
                    break

        currently_alarmed = len(alarmed_person_indices) > 0
        if currently_alarmed and not self._previous_alarmed:
            self.fall_alarm.emit(frame_data.camera_id)
            self.fall_alarm_state.emit(frame_data.camera_id, True)
        elif not currently_alarmed and self._previous_alarmed:
            self.fall_alarm_state.emit(frame_data.camera_id, False)
        self._previous_alarmed = currently_alarmed

        for i, (x1, y1, x2, y2) in enumerate(person_boxes):
            if i in alarmed_person_indices:
                self._draw_detection(frame, x1, y1, x2, y2, (0, 0, 255))
            else:
                self._draw_detection(frame, x1, y1, x2, y2, (0, 255, 0))

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

    # ── Drawing ────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_detection(
        frame: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int] = (0, 255, 0),
    ) -> None:
        """Draw a single detection bounding box."""
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    @staticmethod
    def _boxes_iou(
        ax1: int, ay1: int, ax2: int, ay2: int,
        bx1: int, by1: int, bx2: int, by2: int,
    ) -> float:
        """Compute Intersection over Union of two bounding boxes."""
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

    # ── FPS tracking ───────────────────────────────────────────────────────

    def _update_fps(self) -> None:
        self._fps_counter += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._current_fps = self._fps_counter / elapsed
            self._fps_counter = 0
            self._fps_timer = time.time()


class FallDetectionWorker(QObject):
    """Public façade that manages the internal worker + QThread pair.

    Usage::

        worker = FallDetectionWorker("app/core/ai/weights/fall_detection/best.pt")
        worker.start()
        worker.annotated_frame_ready.connect(some_slot)
        # ...
        worker.submit_frame(frame_data)   # from any thread
        # ...
        worker.stop()
    """

    annotated_frame_ready = Signal(object)  # FrameData
    fall_alarm = Signal(str)  # camera_id
    fall_alarm_state = Signal(str, bool)  # camera_id, active

    def __init__(self, model_path: str = "app/core/ai/weights/fall_detection/best.pt", parent=None) -> None:
        super().__init__(parent)
        self._log = LogService.instance()
        self._thread: Optional[QThread] = None
        self._impl: Optional[_FallDetectionWorkerImpl] = None
        self._model_path = model_path

    def start(self) -> None:
        """Create the QThread, move the worker into it, and start."""
        if self._thread is not None:
            return

        self._thread = QThread()
        self._impl = _FallDetectionWorkerImpl(self._model_path)
        self._impl.moveToThread(self._thread)

        # Connect thread lifecycle
        self._thread.started.connect(self._impl.process_frames)
        self._impl.stopped.connect(self._thread.quit)
        self._impl.stopped.connect(self._impl.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # Forward annotated frames from internal worker to public signal
        self._impl.annotated_frame_ready.connect(self.annotated_frame_ready)

        # Forward fall alarm from internal worker to public signal
        self._impl.fall_alarm.connect(self.fall_alarm)
        self._impl.fall_alarm_state.connect(self.fall_alarm_state)

        # Connect frame submission signal (ensures thread-safe cross-thread calls)
        self._impl.frame_submitted.connect(self._impl.receive_frame)

        self._log.info("Starting FallDetectionWorker thread")
        self._thread.start()

    def stop(self) -> None:
        """Request stop and wait for the thread to finish."""
        if self._impl is not None:
            self._impl.request_stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(5000):
                self._log.warning("FallDetectionWorker thread did not finish in 5s")
        self._impl = None
        self._thread = None
        self._log.info("FallDetectionWorker stopped")

    def submit_frame(self, frame_data) -> None:
        """Submit a frame for processing. Thread-safe via signal."""
        if self._impl is not None:
            self._impl.frame_submitted.emit(frame_data)
