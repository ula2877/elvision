"""
CameraManager + CameraWorker — production-grade camera lifecycle management.

Architecture:
    CameraWorker lives in a dedicated QThread. It runs a blocking decode loop
    (start_stream) that reads frames from a VideoSource. It never manages other
    workers. It emits signals for every state transition.

    CameraManager is the ONLY entity that creates/destroys workers, manages
    threads, and tracks camera state. It receives worker signals, updates its
    central CameraRegistry, and forwards CameraStatus to the UI.

    CameraWidget never directly communicates with CameraWorker or VideoSource.
    It only receives CameraStatus via CameraManager signals.

Thread lifecycle (enforced sequence):
    1. CameraManager creates QThread + CameraWorker
    2. Worker.moveToThread(thread)
    3. thread.started → worker.start_stream (blocking decode loop)
    4. Worker emits state_changed / frame_ready / error signals cross-thread
    5. When start_stream() returns → worker emits stream_ended
    6. CameraManager._on_worker_stream_ended handles ALL cleanup:
       a. Disconnect all signals
       b. Call source.close()
       c. Delete worker and thread via deleteLater from main thread
       d. Update registry

    To stop: CameraManager calls worker.request_stop() → sets _running = False
    → worker's loop exits → start_stream() returns → stream_ended emitted
    → _on_worker_stream_ended cleans up.

NEVER use thread.terminate().
NEVER pop references before thread.wait() returns.
NEVER call deleteLater from inside the dying thread.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from app.core.camera.base import VideoSource
from app.core.camera.factory import VideoSourceFactory
from app.core.camera.registry import CameraRegistry, CameraEntry
from app.core.camera.resilience import ReconnectPolicy, StreamMonitor
from app.core.logging import LogService
from app.models import (
    CameraInfo,
    CameraState,
    CameraStatus,
    ConnectionStats,
    FrameData,
    camera_state_to_status,
)


_FRAME_TIMEOUT_SEC = 5.0
_STOP_TIMEOUT_MS = 5000


class CameraWorker(QObject):
    """Decodes frames from a VideoSource inside a dedicated QThread.

    Lifecycle:
        __init__ → [thread.started] → start_stream() → stream_ended

    Signals:
        state_changed(camera_id, CameraState)
        frame_ready(FrameData)
        first_frame_received(str)
        error_occurred(str, str)
        stats_updated(ConnectionStats)
        stream_ended(str)
    """

    state_changed = Signal(str, object)  # camera_id, CameraState
    frame_ready = Signal(object)  # FrameData
    first_frame_received = Signal(str)  # camera_id
    error_occurred = Signal(str, str)  # camera_id, error_message
    stats_updated = Signal(object)  # ConnectionStats
    stream_ended = Signal(str)  # camera_id

    def __init__(
        self,
        source: VideoSource,
        reconnect_policy: Optional[ReconnectPolicy] = None,
    ) -> None:
        super().__init__()
        self._source = source
        self._camera_id = source.info.id
        self._log = LogService.instance()
        self._monitor = StreamMonitor(self._camera_id)
        self._reconnect_policy = reconnect_policy or ReconnectPolicy()

        self._state = CameraState.IDLE
        self._running = False
        self._first_frame_received = False
        self._last_frame_time = 0.0

    @property
    def state(self) -> CameraState:
        return self._state

    def request_stop(self) -> None:
        """Thread-safe stop request. Called from main thread."""
        self._running = False

    # ── Internal state machine ─────────────────────────────────────────────────

    def _set_state(self, new_state: CameraState) -> None:
        if self._state == new_state:
            return
        old = self._state
        self._state = new_state
        self._log.camera_event(
            self._camera_id,
            "State: %s -> %s" % (old.value, new_state.value),
        )
        self.state_changed.emit(self._camera_id, new_state)

    # ── Main decode loop (runs in worker thread) ──────────────────────────────

    def start_stream(self) -> None:
        """Blocking decode loop. Runs in the worker thread.
        When this method returns, stream_ended is emitted and the thread finishes.
        """
        self._running = True
        self._first_frame_received = False
        self._last_frame_time = 0.0

        try:
            self._set_state(CameraState.CONNECTING)

            if not self._source.open():
                self._set_state(CameraState.ERROR)
                self._monitor.record_error("Failed to open source")
                self._emit_stats()
                self.error_occurred.emit(self._camera_id, "Failed to open source")
                return

            self._set_state(CameraState.CONNECTED)

            # ── Decode loop ────────────────────────────────────────────────
            while self._running:
                try:
                    frame = self._source.read()

                    if frame is not None:
                        self._on_frame_received(frame)
                    else:
                        self._on_frame_timeout()

                except Exception as exc:
                    self._log.error("Read error [%s]: %s", self._camera_id, exc)
                    self._monitor.record_error(str(exc))
                    self._emit_stats()
                    self.error_occurred.emit(self._camera_id, str(exc))
                    self._attempt_reconnect()
                    if not self._running:
                        break

        except Exception as exc:
            self._log.error("Worker fatal [%s]: %s", self._camera_id, exc)
            self._set_state(CameraState.ERROR)
            self._monitor.record_error(str(exc))
            self.error_occurred.emit(self._camera_id, str(exc))

        finally:
            self._set_state(CameraState.STOPPED)
            self._emit_stats()
            self._log.camera_event(self._camera_id, "Stream ended")
            self.stream_ended.emit(self._camera_id)

    def _on_frame_received(self, frame: FrameData) -> None:
        """Handle a valid decoded frame."""
        self._reconnect_policy.reset()
        self._monitor.record_frame()
        self._last_frame_time = time.time()

        if not self._first_frame_received:
            self._first_frame_received = True
            self._set_state(CameraState.STREAMING)
            self.first_frame_received.emit(self._camera_id)

        self.frame_ready.emit(frame)
        self._emit_stats()

    def _on_frame_timeout(self) -> None:
        """Handle a None frame (read returned nothing)."""
        if not self._running:
            return

        current_state = self._state

        if current_state in (CameraState.STREAMING, CameraState.CONNECTED):
            elapsed = (
                time.time() - self._last_frame_time
                if self._last_frame_time
                else _FRAME_TIMEOUT_SEC
            )
            if elapsed >= _FRAME_TIMEOUT_SEC:
                self._set_state(CameraState.BUFFERING)
                self._attempt_reconnect()
        elif current_state == CameraState.BUFFERING:
            self._attempt_reconnect()
        elif current_state == CameraState.RECONNECTING:
            pass  # already reconnecting, wait

    def _attempt_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if not self._source.info.auto_reconnect:
            self._set_state(CameraState.DISCONNECTED)
            self._running = False
            return

        if not self._reconnect_policy.should_retry():
            self._log.warning(
                "Max reconnect attempts reached [%s]", self._camera_id,
            )
            self._set_state(CameraState.ERROR)
            self._monitor.record_error("Max reconnect attempts reached")
            self._emit_stats()
            self.error_occurred.emit(
                self._camera_id, "Max reconnect attempts reached",
            )
            self._running = False
            return

        self._set_state(CameraState.RECONNECTING)
        self._monitor.record_reconnect()

        delay = self._reconnect_policy.next_delay()
        self._log.camera_event(
            self._camera_id,
            "Reconnect in %.1fs (attempt %d)" % (delay, self._reconnect_policy.attempt),
        )

        # Interruptible sleep: check _running every 100ms
        sleep_steps = int(delay * 10)
        for _ in range(sleep_steps):
            if not self._running:
                return
            time.sleep(0.1)

        if not self._running:
            return

        self._set_state(CameraState.CONNECTING)
        self._monitor.reset()

        try:
            if self._source.reconnect():
                self._set_state(CameraState.CONNECTED)
                self._log.camera_event(self._camera_id, "Reconnected")
            else:
                self._log.warning("Reconnect failed [%s]", self._camera_id)
                self._monitor.record_error("Reconnect failed")
        except Exception as exc:
            self._log.error("Reconnect exception [%s]: %s", self._camera_id, exc)
            self._monitor.record_error(str(exc))

    def _emit_stats(self) -> None:
        self.stats_updated.emit(self._monitor.get_stats())


class CameraManager(QObject):
    """Central orchestrator for all camera streams.

    Responsibilities:
        - Create / destroy workers and threads
        - Connect signals
        - Track camera state via CameraRegistry (single source of truth)
        - Forward state to UI as CameraStatus
        - Health monitoring and restart
        - Resource cleanup

    Thread safety rules:
        - All QThread creation/destruction happens in the main thread
        - Worker signals are received via queued connections
        - thread.wait() is always called before releasing references
        - deleteLater is called from the main thread only
        - thread.terminate() is NEVER used
    """

    frame_received = Signal(object)  # FrameData
    camera_status_changed = Signal(str, object)  # camera_id, CameraStatus
    camera_error = Signal(str, str)  # camera_id, error_message
    stats_updated = Signal(object)  # ConnectionStats

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._registry = CameraRegistry()
        self._log = LogService.instance()

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._health_check)
        self._health_timer.setInterval(10_000)

    @property
    def registry(self) -> CameraRegistry:
        return self._registry

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_camera(self, info: CameraInfo) -> str:
        camera_id = info.id
        if camera_id in self._registry:
            self._log.warning("Camera %s already exists", camera_id)
            return camera_id

        try:
            source = VideoSourceFactory.create(info)
        except ValueError as exc:
            self._log.error("Cannot create source for %s: %s", camera_id, exc)
            raise

        policy = ReconnectPolicy(
            initial_interval=info.source_config.reconnect_interval_sec,
            max_attempts=info.source_config.max_reconnect_attempts,
        )
        monitor = StreamMonitor(camera_id)

        entry = CameraEntry(
            info=info,
            source=source,
            reconnect_policy=policy,
            stream_monitor=monitor,
            state=CameraState.IDLE,
        )
        self._registry.add(entry)
        self._start_worker(camera_id)
        self._log.camera_event(camera_id, "Added (type: %s)" % info.source_type.value)
        return camera_id

    def remove_camera(self, camera_id: str) -> None:
        self._stop_worker(camera_id)
        entry = self._registry.remove(camera_id)
        if entry is not None:
            self._log.camera_event(camera_id, "Removed")

    def start_all(self) -> None:
        for entry in self._registry.all_entries():
            self._start_worker(entry.camera_id)
        self._health_timer.start()

    def stop_all(self) -> None:
        self._health_timer.stop()
        for camera_id in list(self._registry.all_camera_ids()):
            self._stop_worker(camera_id)

    def get_source(self, camera_id: str) -> Optional[VideoSource]:
        return self._registry.get_source(camera_id)

    def get_state(self, camera_id: str) -> CameraState:
        return self._registry.get_state(camera_id)

    def camera_count(self) -> int:
        return self._registry.count()

    def active_cameras(self) -> list[str]:
        return self._registry.active_camera_ids()

    def restart_camera(self, camera_id: str) -> None:
        """Stop and restart a camera worker (manual reconnect)."""
        entry = self._registry.get(camera_id)
        if entry is None:
            return
        self._stop_worker(camera_id)
        self._cleanup_worker_entry(entry)
        self._start_worker(camera_id)
        self._log.camera_event(camera_id, "Manual restart")

    # ── Worker management (internal) ───────────────────────────────────────────

    def _start_worker(self, camera_id: str) -> None:
        entry = self._registry.get(camera_id)
        if entry is None:
            return
        if entry.has_worker:
            self._log.warning("Worker already exists for %s", camera_id)
            return

        thread = QThread()
        worker = CameraWorker(entry.source, entry.reconnect_policy)
        worker.moveToThread(thread)

        # ── Signal connections (all queued for cross-thread safety) ─────────
        # Thread lifecycle
        thread.started.connect(worker.start_stream)
        worker.stream_ended.connect(self._on_worker_stream_ended)

        # Frame & state
        worker.frame_ready.connect(self.frame_received.emit)
        worker.state_changed.connect(self._on_worker_state_changed)
        worker.first_frame_received.connect(self._on_first_frame)
        worker.error_occurred.connect(self.camera_error.emit)
        worker.stats_updated.connect(self.stats_updated.emit)

        entry.worker = worker
        entry.thread = thread

        self._log.camera_event(camera_id, "Starting worker thread")
        thread.start()

    def _stop_worker(self, camera_id: str) -> None:
        entry = self._registry.get(camera_id)
        if entry is None:
            return

        worker = entry.worker
        thread = entry.thread

        if worker is None:
            return

        # Step 1: Request stop — the worker's loop will detect this and exit
        entry.state = CameraState.STOPPING
        worker.request_stop()

        # Step 2: If the thread exists, wait for it to finish
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(_STOP_TIMEOUT_MS):
                self._log.warning(
                    "Thread for %s did not finish in %dms",
                    camera_id,
                    _STOP_TIMEOUT_MS,
                )
                # NEVER use thread.terminate() — it causes undefined behavior.
                # The thread will eventually be garbage collected.

        # Step 3: Cleanup — only after thread.wait() returns (thread is stopped)
        self._cleanup_worker_entry(entry)

        self._log.camera_event(camera_id, "Worker stopped")

    def _cleanup_worker_entry(self, entry: CameraEntry) -> None:
        """Clean up worker and thread resources after thread has stopped.

        Must be called from the main thread after thread.wait() returns.
        """
        worker = entry.worker
        thread = entry.thread

        # Disconnect all signals first to prevent any further emissions
        if worker is not None:
            try:
                worker.state_changed.disconnect()
                worker.frame_ready.disconnect()
                worker.first_frame_received.disconnect()
                worker.error_occurred.disconnect()
                worker.stats_updated.disconnect()
                worker.stream_ended.disconnect()
            except (RuntimeError, TypeError):
                pass  # signals already disconnected

        # Close the video source
        try:
            entry.source.close()
        except Exception as exc:
            self._log.error(
                "Error closing source for %s: %s", entry.camera_id, exc,
            )

        # Schedule deletion from the main thread event loop
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

        # Clear references in registry
        entry.worker = None
        entry.thread = None

    # ── Worker signal handlers ─────────────────────────────────────────────────

    def _on_worker_state_changed(self, camera_id: str, state: CameraState) -> None:
        entry = self._registry.get(camera_id)
        if entry is None:
            return
        old_state = entry.state
        entry.state = state
        ui_status = camera_state_to_status(state)
        # Emit only if the UI-facing status actually changed to avoid
        # duplicate updates when _on_worker_stream_ended also emits.
        old_ui = camera_state_to_status(old_state)
        if ui_status != old_ui:
            self.camera_status_changed.emit(camera_id, ui_status)

    def _on_first_frame(self, camera_id: str) -> None:
        entry = self._registry.get(camera_id)
        if entry:
            entry.first_frame_received = True
            entry.last_frame_time = time.time()
        self._log.camera_event(camera_id, "First frame received")

    def _on_worker_stream_ended(self, camera_id: str) -> None:
        """Called when a worker's start_stream() returns.

        At this point the thread is finishing its event loop.
        We do NOT pop references here — _stop_worker handles cleanup
        after thread.wait() returns.

        For unexpected stream endings (errors, disconnects), we schedule
        a restart via QTimer.singleShot to avoid re-entrant cleanup.

        Emits camera_status_changed for terminal states (STOPPING, STOPPED,
        IDLE) so that UI status counters are always in sync.
        """
        entry = self._registry.get(camera_id)
        if entry is None:
            return

        current_state = entry.state
        self._log.camera_event(
            camera_id,
            "Stream ended (state: %s)" % current_state.value,
        )

        if current_state in (CameraState.STOPPING, CameraState.STOPPED):
            # Explicit stop or already stopped — notify UI of terminal state.
            ui_status = camera_state_to_status(current_state)
            self.camera_status_changed.emit(camera_id, ui_status)
            return

        if current_state == CameraState.IDLE:
            # Worker ended in IDLE (health check didn't restart) — notify UI.
            self.camera_status_changed.emit(
                camera_id, camera_state_to_status(CameraState.IDLE),
            )
            return

        # Unexpected stream ending — schedule a restart from the main thread.
        from PySide6.QtCore import QTimer as _QTimer

        _QTimer.singleShot(
            100, lambda cid=camera_id: self._maybe_restart(cid),
        )

    def _maybe_restart(self, camera_id: str) -> None:
        """Attempt to restart a camera that ended unexpectedly.

        Called from main thread after a short delay to ensure the old
        thread has fully finished.

        Emits camera_status_changed for any state transition so that
        UI status counters remain in sync.
        """
        entry = self._registry.get(camera_id)
        if entry is None:
            return

        current_state = entry.state
        if current_state in (CameraState.STOPPING, CameraState.STOPPED):
            return

        # Clean up the old worker/thread references before restarting.
        # The old thread should have finished by now (100ms delay).
        if entry.has_worker:
            self._cleanup_worker_entry(entry)

        source = entry.source
        if source.info.auto_reconnect and current_state != CameraState.ERROR:
            self._log.camera_event(camera_id, "Auto-restarting worker")
            self._start_worker(camera_id)
            # _start_worker → worker.start_stream → CONNECTING →
            # _on_worker_state_changed → camera_status_changed emitted
        else:
            entry.state = CameraState.IDLE
            ui_status = camera_state_to_status(CameraState.IDLE)
            self.camera_status_changed.emit(camera_id, ui_status)

    # ── Health monitoring ──────────────────────────────────────────────────────

    def _health_check(self) -> None:
        for entry in self._registry.all_entries():
            camera_id = entry.camera_id
            state = entry.state

            if entry.has_worker:
                continue  # Worker is alive, skip

            # Worker is dead — decide whether to restart
            if state in (CameraState.STOPPED, CameraState.IDLE, CameraState.ERROR):
                if entry.source.info.auto_reconnect and state != CameraState.ERROR:
                    self._log.camera_event(camera_id, "Health: restarting worker")
                    self._start_worker(camera_id)
