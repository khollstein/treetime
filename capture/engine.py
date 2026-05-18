"""Capture engine — polls active window on a QTimer and writes to SQLite."""

import sqlite3
import sys
import traceback
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from capture.win_info import get_active_window_info
from capture.idle_detect import get_idle_duration_s
from database import queries


class CaptureEngine(QObject):
    """Polls the active window at a fixed interval and stores activity."""

    activity_recorded = Signal(str, str, bool)  # process, title, idle
    offline_ended = Signal(object, object)  # start_dt, end_dt

    # If a poll fires and the gap since last poll exceeds this multiplier
    # times the poll interval, we assume the computer was asleep/locked.
    GAP_MULTIPLIER = 6  # e.g. 5s poll * 6 = 30s gap means offline

    def __init__(self, conn: sqlite3.Connection,
                 poll_interval_ms: int = 5000,
                 idle_threshold_s: int = 300,
                 parent=None):
        super().__init__(parent)
        self._conn = conn
        self._poll_interval_ms = poll_interval_ms
        self._idle_threshold_s = idle_threshold_s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._safe_poll)
        self._last_activity_id = None
        self._last_process = None
        self._last_title = None
        self._last_idle = None
        self._last_poll_time = None
        self._paused = False
        self._consecutive_errors = 0

    def start(self):
        self._last_poll_time = datetime.now()
        self._timer.start(self._poll_interval_ms)

    def stop(self):
        self._timer.stop()

    def set_paused(self, paused: bool):
        self._paused = paused
        if not paused:
            # Reset gap detection so returning from pause doesn't look offline
            self._last_poll_time = datetime.now()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def _safe_poll(self):
        """Wraps _poll() so a single bad poll never breaks the timer."""
        try:
            self._poll()
            self._consecutive_errors = 0
        except Exception as exc:
            self._consecutive_errors += 1
            try:
                sys.stderr.write(
                    f"[Treetime] _poll error ({self._consecutive_errors}): {exc}\n"
                )
                traceback.print_exc(file=sys.stderr)
            except Exception:
                pass
            # Recover: reset dedup state so next poll starts fresh.
            self._last_activity_id = None
            self._last_process = None
            self._last_title = None
            self._last_idle = None
            # Keep _last_poll_time current so we don't falsely trip gap detection
            self._last_poll_time = datetime.now()

    def _poll(self):
        if self._paused:
            self._last_poll_time = datetime.now()
            return

        now = datetime.now()
        poll_seconds = self._poll_interval_ms // 1000

        # ── Gap detection (sleep/lock/hibernate) ──────────────────
        if self._last_poll_time is not None:
            gap = (now - self._last_poll_time).total_seconds()
            gap_threshold = poll_seconds * self.GAP_MULTIPLIER

            if gap > gap_threshold and gap > 60:
                # Computer was offline — insert an offline activity block
                offline_start = self._last_poll_time
                offline_duration = int(gap)

                queries.insert_activity(
                    self._conn,
                    timestamp=offline_start,
                    process="(offline)",
                    title="Computer was locked / asleep",
                    idle=True,
                    duration_s=offline_duration,
                    offline=True,
                )

                # Reset deduplication
                self._last_activity_id = None
                self._last_process = None
                self._last_title = None
                self._last_idle = None

                # Emit so app can react (e.g. show a banner)
                offline_end = now
                self.offline_ended.emit(offline_start, offline_end)

                self._last_poll_time = now
                return

        self._last_poll_time = now

        # ── Normal polling ────────────────────────────────────────
        process, title = get_active_window_info()
        idle = get_idle_duration_s() >= self._idle_threshold_s

        # Privacy mode: mask window titles if configured
        if queries.get_setting(self._conn, "capture_titles", "full") == "process_only":
            title = process.replace(".exe", "")

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
                timestamp=now,
                process=process,
                title=title,
                idle=idle,
                duration_s=poll_seconds,
            )
            self._last_process = process
            self._last_title = title
            self._last_idle = idle

        self.activity_recorded.emit(process, title, idle)
