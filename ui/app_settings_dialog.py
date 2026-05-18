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
            "Changes take effect the next time Treetime starts tracking."
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

    def _on_save(self):
        idle_s = self._idle_spin.value() * 60
        poll_ms = self._poll_spin.value() * 1000
        set_setting(self._conn, "idle_threshold_s", str(idle_s))
        set_setting(self._conn, "poll_interval_ms", str(poll_ms))
        self.settings_changed.emit()
        self.accept()
