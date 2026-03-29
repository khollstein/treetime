"""Main application window with tabs."""

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon

from capture.engine import CaptureEngine
from database.queries import get_setting, set_setting
from ui.timeline.timeline_widget import TimelineWidget
from ui.projects.project_manager import ProjectManager
from ui.reports.report_view import ReportView
from ui.styles import get_theme, set_theme, build_stylesheet, THEMES


class MainWindow(QMainWindow):
    """Main window with Timeline, Projects, and Reports tabs."""

    def __init__(self, conn: sqlite3.Connection, engine: CaptureEngine,
                 parent=None):
        super().__init__(parent)
        self._conn = conn
        self._engine = engine

        self.setWindowTitle("Treetime")
        self.resize(1100, 700)

        from ui.tray import create_app_icon
        self.setWindowIcon(create_app_icon(128))

        # Apply saved theme
        saved_theme = get_setting(conn, "theme", "dark")
        set_theme(saved_theme)
        self.setStyleSheet(build_stylesheet(get_theme()))

        # Tab widget
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # Timeline tab
        self._timeline = TimelineWidget(conn)
        tabs.addTab(self._timeline, "Timeline")

        # Projects tab
        self._projects = ProjectManager(conn)
        tabs.addTab(self._projects, "Projects")

        # Reports tab
        self._reports = ReportView(conn)
        tabs.addTab(self._reports, "Reports")

        # Refresh timeline when tab changes
        self._tabs = tabs
        tabs.currentChanged.connect(self._on_tab_changed)

        # Status bar
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._tracking_dot = QLabel("●")
        self._tracking_dot.setStyleSheet(f"color: {get_theme().success}; font-size: 14px; padding: 0 4px;")
        status_bar.addWidget(self._tracking_dot)

        self._status_label = QLabel("Starting...")
        status_bar.addWidget(self._status_label)

        self._activity_count_label = QLabel()
        self._activity_count_label.setStyleSheet(f"color: {get_theme().text_muted};")
        status_bar.addPermanentWidget(self._activity_count_label)

        # Privacy toggle button
        self._privacy_btn = QPushButton()
        self._privacy_btn.setFixedSize(32, 32)
        self._privacy_btn.clicked.connect(self._toggle_privacy)
        self._update_privacy_button()
        status_bar.addPermanentWidget(self._privacy_btn)

        # Theme toggle button
        self._theme_btn = QPushButton("☀")
        self._theme_btn.setFixedSize(32, 32)
        self._theme_btn.setToolTip("Toggle dark/light mode")
        self._theme_btn.clicked.connect(self._toggle_theme)
        self._update_theme_button()
        status_bar.addPermanentWidget(self._theme_btn)

        # Blink timer
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_dot)
        self._blink_timer.start(1000)

        # Live update
        engine.activity_recorded.connect(self._on_activity_recorded)
        self._poll_count = 0

    def _update_theme_button(self):
        t = get_theme()
        if t.name == "dark":
            self._theme_btn.setText("☀")
            self._theme_btn.setToolTip("Switch to light mode")
        else:
            self._theme_btn.setText("🌙")
            self._theme_btn.setToolTip("Switch to dark mode")

    def _update_privacy_button(self):
        mode = get_setting(self._conn, "capture_titles", "full")
        if mode == "full":
            self._privacy_btn.setText("\U0001F441")  # eye
            self._privacy_btn.setToolTip("Window titles visible — click to mask")
        else:
            self._privacy_btn.setText("\U0001F512")  # lock
            self._privacy_btn.setToolTip("Window titles masked — click to show")

    def _toggle_privacy(self):
        current = get_setting(self._conn, "capture_titles", "full")
        new_mode = "process_only" if current == "full" else "full"
        set_setting(self._conn, "capture_titles", new_mode)
        self._update_privacy_button()

    def _toggle_theme(self):
        t = get_theme()
        new_name = "light" if t.name == "dark" else "dark"
        set_theme(new_name)
        set_setting(self._conn, "theme", new_name)
        new_t = get_theme()
        self.setStyleSheet(build_stylesheet(new_t))
        self._tracking_dot.setStyleSheet(f"color: {new_t.success}; font-size: 14px; padding: 0 4px;")
        self._activity_count_label.setStyleSheet(f"color: {new_t.text_muted};")
        self._update_theme_button()
        # Force repaint of custom widgets
        self._timeline.reload()

    def _blink_dot(self):
        t = get_theme()
        if self._engine.is_paused:
            self._tracking_dot.setStyleSheet(f"color: {t.danger}; font-size: 14px; padding: 0 4px;")
            return
        self._blink_on = not self._blink_on
        if self._blink_on:
            self._tracking_dot.setStyleSheet(f"color: {t.success}; font-size: 14px; padding: 0 4px;")
        else:
            color = t.success + "60"
            self._tracking_dot.setStyleSheet(f"color: {color}; font-size: 14px; padding: 0 4px;")

    def _on_tab_changed(self, index: int):
        if index == 0:
            self._timeline.reload()

    def _on_activity_recorded(self, process: str, title: str, idle: bool):
        self._poll_count += 1
        if idle:
            self._status_label.setText("Idle")
        else:
            display_process = process.replace(".exe", "")
            display_title = title[:60] + "..." if len(title) > 60 else title
            self._status_label.setText(f"Tracking: {display_process} — {display_title}")

        self._activity_count_label.setText(
            f"Polls: {self._poll_count}  |  {datetime.now().strftime('%H:%M:%S')}"
        )

        if self.isVisible() and self._tabs.currentIndex() == 0:
            self._timeline.reload()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
