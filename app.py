"""QApplication subclass and lifecycle management."""

import sys
import ctypes

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from database.connection import get_connection
from database.queries import get_setting, insert_time_entry
from capture.engine import CaptureEngine
from ui.tray import TrayIcon, create_app_icon
from ui.main_window import MainWindow

# Tell Windows this is its own app (not grouped with python.exe in taskbar)
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("canopy.treetime.1")


class TreetimeApp:
    """Application controller — owns the DB, capture engine, tray, and window."""

    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setApplicationName("Treetime")
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setWindowIcon(create_app_icon(128))

        # Database
        self.conn = get_connection()

        # Read settings
        poll_ms = int(get_setting(self.conn, "poll_interval_ms", "5000"))
        idle_s = int(get_setting(self.conn, "idle_threshold_s", "300"))

        # Capture engine
        self.engine = CaptureEngine(self.conn, poll_interval_ms=poll_ms,
                                    idle_threshold_s=idle_s)

        # UI
        self.main_window = MainWindow(self.conn, self.engine)
        self.tray = TrayIcon()

        # Connections
        self.tray.show_window_requested.connect(self._show_main_window)
        self.tray.quit_requested.connect(self._quit)
        self.tray.pause_toggled.connect(self.engine.set_paused)
        self.engine.activity_recorded.connect(self.tray.update_tracking_info)
        self.engine.offline_ended.connect(self._on_offline_ended)

    def run(self) -> int:
        self.tray.show()
        self.engine.start()
        self.main_window.show()
        return self.qt_app.exec()

    def _show_main_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _on_offline_ended(self, start_dt, end_dt):
        """Show Welcome Back dialog if offline duration exceeds threshold."""
        threshold = int(get_setting(self.conn, "offline_welcome_threshold_s", "300"))
        duration = (end_dt - start_dt).total_seconds()
        if duration < threshold:
            return

        from ui.welcome_back_dialog import WelcomeBackDialog
        self._show_main_window()
        dlg = WelcomeBackDialog(self.conn, start_dt, end_dt, parent=self.main_window)
        if dlg.exec():
            project_id, note = dlg.result_data()
            if project_id:
                insert_time_entry(self.conn, project_id, start_dt, end_dt, note)
        # Refresh timeline regardless
        self.main_window.reload_timeline()

    def _quit(self):
        self.engine.stop()
        self.conn.close()
        self.qt_app.quit()
