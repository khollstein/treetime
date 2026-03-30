"""Welcome Back dialog — shown after returning from offline/lock period."""

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFrame,
)
from PySide6.QtCore import Qt

from database import queries
from ui.styles import get_theme


class WelcomeBackDialog(QDialog):
    """Prompts the user to assign offline time to a project."""

    def __init__(self, conn: sqlite3.Connection,
                 start: datetime, end: datetime,
                 parent=None):
        super().__init__(parent)
        self._conn = conn
        self._selected_project_id = None
        self._note = ""

        t = get_theme()
        self.setWindowTitle("Welcome Back!")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header
        header = QLabel("Welcome back!")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {t.text_primary};")
        layout.addWidget(header)

        # Duration info
        duration = end - start
        total_secs = int(duration.total_seconds())
        hours, remainder = divmod(total_secs, 3600)
        minutes = remainder // 60

        if hours > 0:
            dur_text = f"{hours}h {minutes}m"
        else:
            dur_text = f"{minutes} min"

        time_label = QLabel(
            f"You were away <b>{dur_text}</b>"
            f"<br><span style='color: {t.text_muted}'>"
            f"{start.strftime('%H:%M')} \u2014 {end.strftime('%H:%M')}</span>"
        )
        time_label.setStyleSheet("font-size: 14px; padding: 4px 0;")
        layout.addWidget(time_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # Question
        question = QLabel("What were you doing?")
        question.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {t.text_primary};")
        layout.addWidget(question)

        # Recent projects (quick-pick buttons)
        recent_ids = queries.get_recent_project_ids(conn, limit=6)
        if recent_ids:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            for pid in recent_ids:
                project = queries.get_project_by_id(conn, pid)
                if project:
                    btn = QPushButton(project.name)
                    btn.setStyleSheet(
                        f"background-color: {project.color}; color: white; "
                        f"padding: 8px 14px; border-radius: 6px; font-weight: 600; "
                        f"border: none; font-size: 11px;"
                    )
                    btn.clicked.connect(lambda checked, p=project.id: self._quick_pick(p))
                    btn_row.addWidget(btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)

        # Project dropdown
        combo_label = QLabel("Or select:")
        combo_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; margin-top: 4px;")
        layout.addWidget(combo_label)
        self._project_combo = QComboBox()
        all_projects = queries.get_all_projects(conn)
        for p in all_projects:
            display = f"{p.name} ({p.client})" if p.client else p.name
            billable_tag = "" if p.billable else " [non-billable]"
            self._project_combo.addItem(f"{display}{billable_tag}", p.id)
        layout.addWidget(self._project_combo)

        # Note
        note_label = QLabel("Note (optional):")
        note_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; margin-top: 4px;")
        layout.addWidget(note_label)
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("e.g. Client meeting, lunch, travel...")
        layout.addWidget(self._note_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        skip_btn = QPushButton("Leave unassigned")
        skip_btn.clicked.connect(self.reject)

        assign_btn = QPushButton("Assign")
        assign_btn.setObjectName("primary")
        assign_btn.clicked.connect(self._on_assign)

        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(assign_btn)
        layout.addLayout(btn_layout)

    def _quick_pick(self, project_id: int):
        self._selected_project_id = project_id
        self._note = self._note_edit.text()
        self.accept()

    def _on_assign(self):
        idx = self._project_combo.currentIndex()
        if idx >= 0:
            self._selected_project_id = self._project_combo.currentData()
            self._note = self._note_edit.text()
            self.accept()

    def result_data(self) -> tuple[int, str]:
        return self._selected_project_id, self._note
