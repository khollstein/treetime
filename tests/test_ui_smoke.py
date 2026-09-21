"""Smoke test: the windows and dialogs actually build, and the buttons work.

Qt errors — a renamed widget, a signal wired to a method that doesn't exist —
only show up when something is constructed, which no amount of unit testing
the logic will catch. Skipped where PySide6 isn't installed.
"""

import os
import sqlite3
import unittest
from datetime import datetime, timedelta

import tests._helpers  # noqa: F401  (puts the project root on sys.path)
from tests import _win_stubs

_win_stubs.install()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover - depends on the machine
    HAVE_QT = False

from database import queries
from database.schema import init_schema


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class UiSmokeTest(unittest.TestCase):

    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.conn = make_db()
        self.project_id = queries.insert_project(
            self.conn, "P-2842 — Lane Cove", client="North Sydney Council",
            keywords="lane cove", project_number="P-2842",
        )
        start = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        for i in range(12):
            queries.insert_activity(
                self.conn, timestamp=start + timedelta(minutes=5 * i),
                process="qgis-bin.exe", title="P-2842 Lane Cove.qgz",
                idle=False, duration_s=300,
            )

    def test_main_window_builds_and_shows_the_day(self):
        from capture.engine import CaptureEngine
        from ui.main_window import MainWindow

        engine = CaptureEngine(self.conn)
        window = MainWindow(self.conn, engine)
        window.show()
        self.app.processEvents()
        self.assertIn("Treetime", window.windowTitle())
        window.close()

    def test_auto_assign_creates_entries_through_the_widget(self):
        from PySide6.QtWidgets import QMessageBox
        from ui.timeline import timeline_widget as tw

        # The button reports its result in a modal; answer it immediately.
        original = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            widget = tw.TimelineWidget(self.conn)
            widget._auto_assign()
        finally:
            QMessageBox.information = original

        entries = queries.get_time_entries_for_day(self.conn,
                                                   datetime.now().date())
        self.assertEqual(len(entries), 1)

    def test_the_timeline_paints(self):
        """paintEvent draws rule-match dots, so it must survive a real day."""
        from ui.timeline import timeline_widget as tw

        widget = tw.TimelineWidget(self.conn)
        widget.resize(1000, 600)
        self.assertFalse(widget.grab().isNull())

    def test_push_button_reports_what_came_back(self):
        from PySide6.QtWidgets import QMessageBox
        from capture.engine import CaptureEngine
        from ui import main_window as mw

        queries.set_setting(self.conn, "fieldflow_api_key", "k")
        queries.set_setting(self.conn, "fieldflow_person_email", "a@b.com")

        shown = []
        original_push = mw.fieldflow_time.push_recent
        original_info = QMessageBox.information
        mw.fieldflow_time.push_recent = lambda *a, **k: {
            "sent": 3, "skipped": 1, "deleted": 0, "failed": 0,
            "problems": [], "errors": [],
        }
        QMessageBox.information = staticmethod(
            lambda parent, title, text, *a, **k: shown.append((title, text))
        )
        try:
            window = mw.MainWindow(self.conn, CaptureEngine(self.conn))
            window._push_btn.click()
            window.close()
        finally:
            mw.fieldflow_time.push_recent = original_push
            QMessageBox.information = original_info

        self.assertEqual(len(shown), 1)
        self.assertIn("Sent 3 entries", shown[0][1])
        self.assertIn("1 already up to date", shown[0][1])
        self.assertTrue(queries.get_setting(self.conn, "fieldflow_last_push"))

    def test_settings_dialogs_build_and_save(self):
        from ui.app_settings_dialog import AppSettingsDialog
        from ui.fieldflow_settings import FieldFlowSettingsDialog

        app_dlg = AppSettingsDialog(self.conn)
        app_dlg._gap_spin.setValue(4)
        app_dlg._switch_spin.setValue(30)
        app_dlg._min_block_spin.setValue(2)
        app_dlg._on_save()
        self.assertEqual(queries.get_setting(self.conn, "continuity_gap_s"), "240")
        self.assertEqual(queries.get_setting(self.conn, "continuity_switch_s"), "30")
        self.assertEqual(queries.get_setting(self.conn, "min_block_s"), "120")

        ff_dlg = FieldFlowSettingsDialog(self.conn)
        ff_dlg._email_edit.setText("matt@canopyconsulting.com.au")
        ff_dlg._push_auto_check.setChecked(True)
        ff_dlg._push_hour_spin.setValue(18)
        ff_dlg._save()
        self.assertEqual(
            queries.get_setting(self.conn, "fieldflow_person_email"),
            "matt@canopyconsulting.com.au",
        )
        self.assertEqual(queries.get_setting(self.conn, "fieldflow_push_auto"), "1")
        self.assertEqual(queries.get_setting(self.conn, "fieldflow_push_hour"), "18")

    def test_project_dialog_round_trips_the_project_number(self):
        from ui.projects.project_manager import ProjectEditDialog, ProjectManager

        dlg = ProjectEditDialog(name="P-3100 — Elm St", project_number="P-3100")
        self.assertEqual(dlg.result_data()["project_number"], "P-3100")

        manager = ProjectManager(self.conn)
        self.assertEqual(manager._model.rowCount(), 1)

    def test_reports_tab_builds(self):
        from ui.reports.report_view import ReportView

        view = ReportView(self.conn)
        view._refresh()

    def test_nightly_push_is_skipped_when_it_is_not_configured(self):
        from capture.engine import CaptureEngine
        from ui.main_window import MainWindow

        window = MainWindow(self.conn, CaptureEngine(self.conn))
        window._maybe_auto_push()  # no key, no email — must not raise
        self.assertEqual(queries.get_setting(self.conn, "fieldflow_last_push"), "")
        window.close()


if __name__ == "__main__":
    unittest.main()
