"""End to end: captured activity rows through to time entries.

Exercises the same path the Timeline's "Auto-assign rules" button takes,
against a real database, without needing Qt.
"""

import sqlite3
import unittest
from datetime import date, datetime, timedelta

import tests._helpers  # noqa: F401  (puts the project root on sys.path)

from core.blocks import BlockOptions, build_blocks
from core.matching import ProjectMatcher
from database import queries
from database.schema import init_schema
from ui.timeline.timeline_model import TimelineModel


DAY = date(2026, 9, 21)
NINE_AM = datetime(2026, 9, 21, 9, 0)
POLL_S = 5


class AutoAssignTest(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.lane_cove = queries.insert_project(
            self.conn, "P-2842 — Lane Cove", project_number="P-2842")

    def record(self, minute_offset, minutes, process, title, idle=False,
               offline=False):
        """Write an activity block the way the capture engine would."""
        queries.insert_activity(
            self.conn,
            timestamp=NINE_AM + timedelta(minutes=minute_offset),
            process=process,
            title=title,
            idle=idle,
            duration_s=int(minutes * 60),
            offline=offline,
        )

    def auto_assign(self, options=None):
        model = TimelineModel(self.conn)
        model.load_day(DAY)
        matcher = ProjectMatcher(queries.get_all_projects(self.conn))
        covered = [(e.start_time, e.end_time)
                   for e in queries.get_time_entries_for_day(self.conn, DAY)]
        result = build_blocks(model.activity_segments, matcher,
                              options or BlockOptions.from_settings(self.conn),
                              covered)
        for block in result.blocks:
            queries.insert_time_entry(self.conn, block.project.id,
                                      block.start, block.end)
        return result

    def test_a_morning_of_flicking_between_windows_is_one_entry(self):
        # Two hours on the job, interrupted the way a real morning is.
        self.record(0, 25, "qgis-bin.exe", "P-2842 Lane Cove.qgz")
        self.record(25, 2, "outlook.exe", "Inbox — Outlook")
        self.record(27, 40, "winword.exe", "P-2842 arborist report.docx")
        self.record(67, 1, "chrome.exe", "Bureau of Meteorology")
        self.record(68, 3, "", "", idle=True)
        self.record(71, 49, "qgis-bin.exe", "P2842_site_plan.qgz")

        result = self.auto_assign()

        entries = queries.get_time_entries_for_day(self.conn, DAY)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].start_time, NINE_AM)
        self.assertEqual(entries[0].end_time, NINE_AM + timedelta(minutes=120))
        # Outlook, then the browser-and-idle stretch that runs together.
        self.assertEqual(result.bridged_count, 2)
        self.assertEqual(result.bridged_s, 6 * 60)

    def test_lunch_breaks_the_day_in_two(self):
        self.record(0, 60, "qgis-bin.exe", "P-2842 Lane Cove.qgz")
        self.record(60, 45, "(offline)", "Computer was locked / asleep",
                    idle=True, offline=True)
        self.record(105, 60, "qgis-bin.exe", "P-2842 Lane Cove.qgz")

        self.auto_assign()

        entries = queries.get_time_entries_for_day(self.conn, DAY)
        self.assertEqual(len(entries), 2)

    def test_running_auto_assign_twice_does_not_duplicate_entries(self):
        self.record(0, 60, "qgis-bin.exe", "P-2842 Lane Cove.qgz")
        self.auto_assign()
        second = self.auto_assign()

        self.assertEqual(second.blocks, [])
        self.assertEqual(len(queries.get_time_entries_for_day(self.conn, DAY)), 1)

    def test_time_already_assigned_by_hand_is_left_alone(self):
        self.record(0, 120, "qgis-bin.exe", "P-2842 Lane Cove.qgz")
        queries.insert_time_entry(
            self.conn, self.lane_cove,
            NINE_AM + timedelta(minutes=30), NINE_AM + timedelta(minutes=60),
            "typed by hand",
        )

        self.auto_assign()

        entries = sorted(queries.get_time_entries_for_day(self.conn, DAY),
                         key=lambda e: e.start_time)
        self.assertEqual([(e.start_time, e.end_time) for e in entries], [
            (NINE_AM, NINE_AM + timedelta(minutes=30)),
            (NINE_AM + timedelta(minutes=30), NINE_AM + timedelta(minutes=60)),
            (NINE_AM + timedelta(minutes=60), NINE_AM + timedelta(minutes=120)),
        ])

    def test_five_second_polls_add_up_to_one_block(self):
        """The capture engine writes many rows when titles keep changing."""
        for i in range(120):  # ten minutes of alternating window titles
            self.record(i * POLL_S / 60.0, POLL_S / 60.0, "qgis-bin.exe",
                        f"P-2842 Lane Cove.qgz — layer {i % 3}")

        self.auto_assign()

        entries = queries.get_time_entries_for_day(self.conn, DAY)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].end_time, NINE_AM + timedelta(minutes=10))

    def test_settings_control_how_forgiving_the_grouping_is(self):
        self.record(0, 30, "qgis-bin.exe", "P-2842 Lane Cove.qgz")
        self.record(30, 4, "outlook.exe", "Inbox — Outlook")
        self.record(34, 30, "qgis-bin.exe", "P-2842 Lane Cove.qgz")

        queries.set_setting(self.conn, "continuity_gap_s", "60")
        options = BlockOptions.from_settings(self.conn)
        self.assertEqual(options.gap_s, 60)

        self.auto_assign(options)
        self.assertEqual(len(queries.get_time_entries_for_day(self.conn, DAY)), 2)

    def test_unmatched_day_creates_nothing(self):
        self.record(0, 60, "spotify.exe", "Discover Weekly")
        self.auto_assign()
        self.assertEqual(queries.get_time_entries_for_day(self.conn, DAY), [])


if __name__ == "__main__":
    unittest.main()
