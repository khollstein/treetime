"""Capture engine — polls active window on a QTimer and writes to SQLite."""

import sqlite3
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from capture.win_info import get_active_window_info
from capture.idle_detect import get_idle_duration_s
from database import queries


class CaptureEngine(QObject):
    """Polls the active window at a fixed interval and stores activity."""

    activity_recorded = Signal(str, str, bool)  # process, title, idle
    offline_ended = Signal(object, object)  # start_dt, end_dt

    def __init__(self, conn: sqlite3.Connection,
                 poll_interval_ms: int = 5000,
                 idle_threshold_s: int = 300,
                 parent=None):
        super().__init__(parent)
        self._conn = conn
        self._poll_interval_ms = poll_interval_ms
        self._idle_threshold_s = idle_threshold_s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._last_activity_id = None
        self._last_process = None
        self._last_title = None
        self._last_idle = None
        self._paused = False
        # Offline state
        self._is_offline = False
        self._offline_start = None
        self._offline_activity_id = None

    def start(self):
        self._timer.start(self._poll_interval_ms)

    def stop(self):
        self._timer.stop()

    def set_paused(self, paused: bool):
        self._paused = paused

    @property
    def is_paused(self) -> bool:
        return self._paused

    def on_session_locked(self):
        """Called when the Windows session is locked."""
        if self._is_offline:
            return
        self._is_offline = True
        self._offline_start = datetime.now()
        # Reset deduplication state
        self._last_activity_id = None
        self._last_process = None
        self._last_title = None
        self._last_idle = None
        # Insert an offline activity row
        self._offline_activity_id = queries.insert_activity(
            self._conn,
            timestamp=self._offline_start,
            process="(offline)",
            title="Screen locked",
            idle=True,
            duration_s=0,
            offline=True,
        )

    def on_session_unlocked(self):
        """Called when the Windows session is unlocked."""
        if not self._is_offline:
            return
        end_time = datetime.now()
        start_time = self._offline_start or end_time
        duration = int((end_time - start_time).total_seconds())

        # Update the offline activity row with the actual duration
        if self._offline_activity_id and duration > 0:
            queries.set_activity_duration(
                self._conn, self._offline_activity_id, duration
            )

        self._is_offline = False
        self._offline_activity_id = None

        # Emit signal so app can show Welcome Back dialog
        self.offline_ended.emit(start_time, end_time)

    def _poll(self):
        if self._paused or self._is_offline:
            return

        process, title = get_active_window_info()
        idle = get_idle_duration_s() >= self._idle_threshold_s

        # Privacy mode: mask window titles if configured
        if queries.get_setting(self._conn, "capture_titles", "full") == "process_only":
            title = process.replace(".exe", "")
        poll_seconds = self._poll_interval_ms // 1000

        # Deduplication: if same window and same idle state, extend duration
        if (self._last_activity_id is not None
                and process == self._last_process
                and title == self._last_title
                and idle == self._last_idle):
            queries.update_activity_duration(
                self._conn, self._last_activity_id, poll_seconds
            )
        else:
            self._last_activity_id = queries.insert_activity(
                self._conn,
                timestamp=datetime.now(),
                process=process,
                title=title,
                idle=idle,
                duration_s=poll_seconds,
            )
            self._last_process = process
            self._last_title = title
            self._last_idle = idle

        self.activity_recorded.emit(process, title, idle)
