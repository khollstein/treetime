"""Dialog for assigning a time range to a project, with keyword auto-matching."""

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCompleter, QLineEdit, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from database import queries
from ui.styles import get_theme


class AssignmentDialog(QDialog):
    """Quick-pick dialog with keyword-based auto-suggestion."""

    def __init__(self, conn: sqlite3.Connection,
                 start: datetime, end: datetime,
                 activities: dict[str, float],
                 parent=None):
        super().__init__(parent)
        self._conn = conn
        self._selected_project_id = None
        self._note = ""

        t = get_theme()
        self.setWindowTitle("Assign to Project")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # Time range header
        duration = end - start
        minutes = round(duration.total_seconds() / 60)
        hours, mins = divmod(minutes, 60)
        time_str = f"{hours}h {mins}m" if hours else f"{mins}m"

        header = QLabel(
            f"<b>{start.strftime('%H:%M')} — {end.strftime('%H:%M')}</b>  "
            f"<span style='color: {t.text_muted}'>({time_str})</span>"
        )
        header.setStyleSheet("font-size: 15px; padding: 4px 0;")
        layout.addWidget(header)

        # Activities summary
        if activities:
            summary_parts = []
            for proc, secs in sorted(activities.items(), key=lambda x: -x[1]):
                summary_parts.append(f"{proc}: {max(1, round(secs / 60))}m")
            summary_label = QLabel("  |  ".join(summary_parts[:5]))
            summary_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
            summary_label.setWordWrap(True)
            layout.addWidget(summary_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # Auto-match: check if keywords match any project
        auto_match = None
        all_text = " ".join(f"{proc} {title}" for proc, title in
                           [(p, p) for p in activities.keys()])
        # Build a combined text from the activities for matching
        combined_text = ""
        for proc_name in activities.keys():
            combined_text += f" {proc_name}"
        if combined_text:
            auto_match = queries.match_project_by_keywords(conn, combined_text, combined_text)

        if auto_match:
            match_label = QLabel(f"Auto-detected:")
            match_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; margin-top: 4px;")
            layout.addWidget(match_label)

            match_btn = QPushButton(f"  {auto_match.name}  ")
            match_btn.setStyleSheet(
                f"background-color: {auto_match.color}; color: white; "
                f"padding: 10px 16px; border-radius: 6px; font-weight: bold; "
                f"font-size: 13px; border: none; text-align: left;"
            )
            match_btn.clicked.connect(lambda: self._quick_pick(auto_match.id))
            layout.addWidget(match_btn)

            layout.addWidget(QLabel(""))  # spacer

        # Recent projects (quick-pick buttons)
        recent_ids = queries.get_recent_project_ids(conn, limit=5)
        if recent_ids:
            recent_label = QLabel("Recent:")
            recent_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
            layout.addWidget(recent_label)
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(6)
            for pid in recent_ids:
                if auto_match and pid == auto_match.id:
                    continue  # Already shown above
                project = queries.get_project_by_id(conn, pid)
                if project:
                    btn = QPushButton(project.name)
                    btn.setStyleSheet(
                        f"background-color: {project.color}; color: white; "
                        f"padding: 8px 14px; border-radius: 6px; font-weight: 600; "
                        f"border: none; font-size: 11px;"
                    )
                    btn.clicked.connect(lambda checked, p=project.id: self._quick_pick(p))
                    btn_layout.addWidget(btn)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)

        # Project dropdown + new project button
        combo_label = QLabel("Or select project:")
        combo_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; margin-top: 8px;")
        layout.addWidget(combo_label)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(6)
        self._project_combo = QComboBox()
        self._project_combo.setEditable(True)
        self._project_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._project_combo.lineEdit().setPlaceholderText("Type to search projects...")
        self._project_combo.lineEdit().setClearButtonEnabled(True)

        # Substring (contains) matching so typing "elm" finds "42 Elm St"
        completer = self._project_combo.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self._all_projects = queries.get_all_projects(conn)
        selected_index = 0
        for i, p in enumerate(self._all_projects):
            display = f"{p.name} ({p.client})" if p.client else p.name
            self._project_combo.addItem(display, p.id)
            if auto_match and p.id == auto_match.id:
                selected_index = i
        if auto_match:
            self._project_combo.setCurrentIndex(selected_index)
        combo_row.addWidget(self._project_combo, 1)

        new_proj_btn = QPushButton("+ New")
        new_proj_btn.setToolTip("Create a new project")
        new_proj_btn.setFixedWidth(68)
        new_proj_btn.clicked.connect(self._on_new_project)
        combo_row.addWidget(new_proj_btn)
        layout.addLayout(combo_row)

        # Note
        note_label = QLabel("Note (optional):")
        note_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; margin-top: 4px;")
        layout.addWidget(note_label)
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("What were you working on?")
        layout.addWidget(self._note_edit)

        # Buttons
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        assign_btn = QPushButton("Assign")
        assign_btn.setObjectName("primary")
        assign_btn.clicked.connect(self._on_assign)
        btn_layout2.addWidget(cancel_btn)
        btn_layout2.addWidget(assign_btn)
        layout.addLayout(btn_layout2)

    def _quick_pick(self, project_id: int):
        self._selected_project_id = project_id
        self._note = self._note_edit.text()
        self.accept()

    def _on_new_project(self):
        """Open ProjectEditDialog, create the project, and select it in combo."""
        from ui.projects.project_manager import ProjectEditDialog
        dlg = ProjectEditDialog(parent=self)
        if not dlg.exec():
            return
        data = dlg.result_data()
        name = data["name"]
        client = data["client"]
        color = data["color"]
        keywords = data["keywords"]
        billable = data["billable"]
        if not name.strip():
            return
        new_id = queries.insert_project(
            self._conn,
            name=name.strip(),
            client=client.strip(),
            color=color,
            keywords=keywords.strip(),
            billable=billable,
        )
        # Refresh combo
        display = f"{name} ({client})" if client else name
        self._project_combo.addItem(display, new_id)
        self._project_combo.setCurrentIndex(self._project_combo.count() - 1)

    def _on_assign(self):
        idx = self._project_combo.currentIndex()
        if idx < 0:
            # Editable combo: user may have typed without selecting from popup.
            # Try to resolve what they typed to an exact item.
            typed = self._project_combo.currentText().strip().lower()
            for i in range(self._project_combo.count()):
                if self._project_combo.itemText(i).lower() == typed:
                    idx = i
                    break
        if idx >= 0:
            self._selected_project_id = self._project_combo.itemData(idx)
            self._note = self._note_edit.text()
            self.accept()

    def result_data(self) -> tuple[int, str]:
        return self._selected_project_id, self._note
