"""Application settings dialog — idle threshold, poll interval, etc."""

import sqlite3

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QPushButton,
    QSpinBox, QHBoxLayout, QFrame,
)
from PySide6.QtCore import Qt, Signal

from database.queries import get_setting, set_setting


class AppSettingsDialog(QDialog):
    """Configure core capture behaviour (idle threshold, poll interval)."""

    settings_changed = Signal()  # emitted when the user saves

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("Treetime Settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        header = QLabel("Capture settings")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        sub = QLabel(
            "How often the active window is sampled, and how forgiving "
            "auto-assign is when you flick between windows."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888;")
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Idle threshold
        self._idle_spin = QSpinBox()
        self._idle_spin.setRange(1, 120)
        self._idle_spin.setSuffix(" minutes")
        self._idle_spin.setToolTip(
            "How long the mouse/keyboard must be idle before the time\n"
            "is shown as 'away' in the Memory Aid column."
        )
        idle_s = int(get_setting(conn, "idle_threshold_s", "300"))
        self._idle_spin.setValue(max(1, idle_s // 60))
        form.addRow("Idle threshold:", self._idle_spin)

        idle_help = QLabel(
            "How many minutes without keyboard/mouse input before\n"
            "time is marked as away."
        )
        idle_help.setStyleSheet("font-size: 10px; color: #888;")
        form.addRow("", idle_help)

        # Poll interval
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(1, 60)
        self._poll_spin.setSuffix(" seconds")
        self._poll_spin.setToolTip(
            "How often Treetime checks the active window.\n"
            "Lower = more accurate, higher = less CPU."
        )
        poll_ms = int(get_setting(conn, "poll_interval_ms", "5000"))
        self._poll_spin.setValue(max(1, poll_ms // 1000))
        form.addRow("Poll interval:", self._poll_spin)

        poll_help = QLabel(
            "How often Treetime samples the active window.\n"
            "Default is every 5 seconds."
        )
        poll_help.setStyleSheet("font-size: 10px; color: #888;")
        form.addRow("", poll_help)

        layout.addLayout(form)

        # ── Time blocks ──────────────────────────────────────────────
        block_line = QFrame()
        block_line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(block_line)

        block_header = QLabel("Time blocks")
        block_header.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(block_header)

        block_sub = QLabel(
            "Auto-assign keeps a job in one block across short interruptions, "
            "instead of splitting it at every window switch and dropping the "
            "pieces."
        )
        block_sub.setWordWrap(True)
        block_sub.setStyleSheet("color: #888;")
        layout.addWidget(block_sub)

        block_form = QFormLayout()
        block_form.setSpacing(10)
        block_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._gap_spin = QSpinBox()
        self._gap_spin.setRange(0, 60)
        self._gap_spin.setSuffix(" minutes")
        self._gap_spin.setValue(self._minutes("continuity_gap_s", 300))
        self._gap_spin.setToolTip(
            "Checking email or sitting idle for less than this, with the same\n"
            "job recognised on both sides, stays part of that job's block."
        )
        block_form.addRow("Bridge gaps up to:", self._gap_spin)

        self._switch_spin = QSpinBox()
        self._switch_spin.setRange(0, 600)
        self._switch_spin.setSuffix(" seconds")
        self._switch_spin.setValue(self._seconds("continuity_switch_s", 60))
        self._switch_spin.setToolTip(
            "A glance at another job shorter than this, surrounded by the job\n"
            "you were on, is counted to the job you were on. 0 turns this off."
        )
        block_form.addRow("Absorb other-job glances under:", self._switch_spin)

        self._min_block_spin = QSpinBox()
        self._min_block_spin.setRange(0, 60)
        self._min_block_spin.setSuffix(" minutes")
        self._min_block_spin.setValue(self._minutes("min_block_s", 60))
        self._min_block_spin.setToolTip(
            "Blocks shorter than this are not turned into time entries."
        )
        block_form.addRow("Ignore blocks under:", self._min_block_spin)

        layout.addLayout(block_form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _minutes(self, key: str, default_s: int) -> int:
        return max(0, self._seconds(key, default_s) // 60)

    def _seconds(self, key: str, default_s: int) -> int:
        try:
            return max(0, int(get_setting(self._conn, key, str(default_s))
                              or default_s))
        except (TypeError, ValueError):
            return default_s

    def _on_save(self):
        idle_s = self._idle_spin.value() * 60
        poll_ms = self._poll_spin.value() * 1000
        set_setting(self._conn, "idle_threshold_s", str(idle_s))
        set_setting(self._conn, "poll_interval_ms", str(poll_ms))
        set_setting(self._conn, "continuity_gap_s", str(self._gap_spin.value() * 60))
        set_setting(self._conn, "continuity_switch_s", str(self._switch_spin.value()))
        set_setting(self._conn, "min_block_s", str(self._min_block_spin.value() * 60))
        self.settings_changed.emit()
        self.accept()
