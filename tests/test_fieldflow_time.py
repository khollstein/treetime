"""Pushing time to FieldFlow: safe to resend, honest about what failed."""

import json
import sqlite3
import unittest
from datetime import date, datetime, timedelta

import tests._helpers  # noqa: F401  (puts the project root on sys.path)

from database import queries
from database.schema import init_schema
from integrations import fieldflow_time as ft


TODAY = date(2026, 9, 21)


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def add_entry(conn, project_id, start_hour=8, minutes=210, note="Tree inspection"):
    start = datetime(2026, 9, 21, start_hour, 5)
    return queries.insert_time_entry(
        conn, project_id, start, start + timedelta(minutes=minutes), note
    )


class RecordingTransport:
    """Stands in for the network; records every batch it is handed."""

    def __init__(self, status=200, body=None, error=None):
        self.status = status
        self.body = body if body is not None else json.dumps({"received": 0})
        self.error = error
        self.calls = []

    def __call__(self, url, api_key, body):
        self.calls.append({
            "url": url,
            "api_key": api_key,
            "entries": json.loads(body.decode("utf-8"))["entries"],
        })
        if self.error:
            raise self.error
        return self.status, self.body

    @property
    def sent_entries(self):
        return [e for call in self.calls for e in call["entries"]]


class PayloadTest(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()
        self.project_id = queries.insert_project(
            self.conn, "P-2842 — Lane Cove", client="North Sydney Council",
            keywords="lane cove", project_number="P-2842",
        )
        self.entry_id = add_entry(self.conn, self.project_id)

    def test_payload_carries_the_five_fields_that_matter(self):
        row = queries.get_entries_for_push(self.conn, TODAY, TODAY)[0]
        payload, problem = ft.build_entry_payload(
            row, "matthew@canopyconsulting.com.au", "3f9a2b71"
        )
        self.assertIsNone(problem)
        self.assertEqual(payload["external_id"], f"tt-3f9a2b71-{self.entry_id}")
        self.assertEqual(payload["project_number"], "P-2842")
        self.assertEqual(payload["person_email"], "matthew@canopyconsulting.com.au")
        self.assertEqual(payload["minutes"], 210)
        self.assertEqual(payload["description"], "Tree inspection")
        self.assertTrue(payload["billable"])

    def test_started_at_carries_a_utc_offset(self):
        row = queries.get_entries_for_push(self.conn, TODAY, TODAY)[0]
        payload, _ = ft.build_entry_payload(row, "a@b.com", "x")
        parsed = datetime.fromisoformat(payload["started_at"])
        self.assertIsNotNone(parsed.tzinfo)

    def test_entry_without_a_project_number_is_reported_not_sent(self):
        no_number = queries.insert_project(self.conn, "Admin", keywords="email")
        add_entry(self.conn, no_number, start_hour=13)
        rows = [r for r in queries.get_entries_for_push(self.conn, TODAY, TODAY)
                if r["project_id"] == no_number]
        payload, problem = ft.build_entry_payload(rows[0], "a@b.com", "x")
        self.assertIsNone(payload)
        self.assertIn("no project number", problem)

    def test_project_number_is_recovered_from_the_display_name(self):
        legacy = queries.insert_project(self.conn, "P-3100 — Elm St")
        add_entry(self.conn, legacy, start_hour=14)
        row = [r for r in queries.get_entries_for_push(self.conn, TODAY, TODAY)
               if r["project_id"] == legacy][0]
        payload, _ = ft.build_entry_payload(row, "a@b.com", "x")
        self.assertEqual(payload["project_number"], "P-3100")

    def test_missing_email_blocks_the_push(self):
        row = queries.get_entries_for_push(self.conn, TODAY, TODAY)[0]
        payload, problem = ft.build_entry_payload(row, "", "x")
        self.assertIsNone(payload)
        self.assertIn("email", problem)

    def test_hash_changes_when_the_entry_changes(self):
        row = queries.get_entries_for_push(self.conn, TODAY, TODAY)[0]
        first, _ = ft.build_entry_payload(row, "a@b.com", "x")
        row["note"] = "Rewritten"
        second, _ = ft.build_entry_payload(row, "a@b.com", "x")
        self.assertNotEqual(ft.payload_hash(first), ft.payload_hash(second))


class PushTest(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()
        queries.set_setting(self.conn, "fieldflow_person_email", "matt@example.com")
        self.project_id = queries.insert_project(
            self.conn, "P-2842 — Lane Cove", project_number="P-2842",
        )
        self.entry_id = add_entry(self.conn, self.project_id)

    def push(self, transport, **kwargs):
        return ft.push_time_entries(self.conn, "test-key", TODAY, TODAY,
                                    transport=transport, **kwargs)

    def test_a_push_sends_one_batch_with_the_api_key(self):
        transport = RecordingTransport()
        result = self.push(transport)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["api_key"], "test-key")

    def test_resending_is_a_no_op_until_something_changes(self):
        first = RecordingTransport()
        self.push(first)

        second = RecordingTransport()
        result = self.push(second)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(second.calls, [])

        queries.update_time_entry(
            self.conn, self.entry_id, self.project_id,
            datetime(2026, 9, 21, 8, 5), datetime(2026, 9, 21, 12, 5),
            "Revised note",
        )
        third = RecordingTransport()
        result = self.push(third)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(third.sent_entries[0]["minutes"], 240)

    def test_force_resends_everything(self):
        self.push(RecordingTransport())
        transport = RecordingTransport()
        self.assertEqual(self.push(transport, force=True)["sent"], 1)

    def test_external_id_is_stable_across_pushes(self):
        first = RecordingTransport()
        self.push(first)
        second = RecordingTransport()
        self.push(second, force=True)
        self.assertEqual(first.sent_entries[0]["external_id"],
                         second.sent_entries[0]["external_id"])

    def test_a_failed_push_is_not_recorded_as_sent(self):
        failing = RecordingTransport(status=500, body="boom")
        result = self.push(failing)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(result["errors"])

        retry = RecordingTransport()
        self.assertEqual(self.push(retry)["sent"], 1)

    def test_per_entry_rejections_are_surfaced_and_retried(self):
        external_id = ft.external_id_for(ft.get_install_id(self.conn), self.entry_id)
        rejecting = RecordingTransport(body=json.dumps({
            "results": [{"external_id": external_id, "status": "rejected",
                         "reason": "no project P-2842"}]
        }))
        result = self.push(rejecting)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertIn("no project P-2842", result["problems"][0])

        retry = RecordingTransport()
        self.assertEqual(self.push(retry)["sent"], 1)

    def test_an_empty_response_body_counts_as_accepted(self):
        self.assertEqual(self.push(RecordingTransport(status=204, body=""))["sent"], 1)

    def test_deleting_a_pushed_entry_withdraws_it_once(self):
        self.push(RecordingTransport())
        queries.delete_time_entry(self.conn, self.entry_id)

        transport = RecordingTransport()
        result = self.push(transport)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(transport.sent_entries[0]["deleted"], True)

        again = RecordingTransport()
        self.assertEqual(self.push(again)["deleted"], 0)
        self.assertEqual(again.calls, [])

    def test_deleting_an_unpushed_entry_says_nothing_to_fieldflow(self):
        queries.delete_time_entry(self.conn, self.entry_id)
        transport = RecordingTransport()
        result = self.push(transport)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(transport.calls, [])

    def test_unmatchable_entries_are_reported_but_do_not_block_the_batch(self):
        orphan = queries.insert_project(self.conn, "Admin", keywords="email")
        add_entry(self.conn, orphan, start_hour=14)
        transport = RecordingTransport()
        result = self.push(transport)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(result["problems"]), 1)

    def test_no_api_key_is_an_error_not_a_crash(self):
        result = ft.push_time_entries(self.conn, "", TODAY, TODAY,
                                      transport=RecordingTransport())
        self.assertEqual(result["errors"], ["No FieldFlow API key configured."])

    def test_batches_are_chunked(self):
        for hour in range(9, 20):
            add_entry(self.conn, self.project_id, start_hour=hour, minutes=30)
        original = ft.BATCH_SIZE
        ft.BATCH_SIZE = 5
        try:
            transport = RecordingTransport()
            result = self.push(transport)
        finally:
            ft.BATCH_SIZE = original
        self.assertEqual(result["sent"], 12)
        self.assertEqual(len(transport.calls), 3)

    def test_push_recent_covers_the_lookback_window(self):
        old = queries.insert_time_entry(
            self.conn, self.project_id,
            datetime(2026, 9, 1, 9, 0), datetime(2026, 9, 1, 10, 0), "old",
        )
        transport = RecordingTransport()
        ft.push_recent(self.conn, "k", lookback_days=7, today=TODAY,
                       transport=transport)
        sent_ids = {e["external_id"] for e in transport.sent_entries}
        install = ft.get_install_id(self.conn)
        self.assertIn(ft.external_id_for(install, self.entry_id), sent_ids)
        self.assertNotIn(ft.external_id_for(install, old), sent_ids)

    def test_install_id_is_stable(self):
        self.assertEqual(ft.get_install_id(self.conn), ft.get_install_id(self.conn))


class ExportTest(unittest.TestCase):
    """The CSV fallback carries the same fields as a push."""

    def setUp(self):
        self.conn = make_db()
        queries.set_setting(self.conn, "fieldflow_person_email", "matt@example.com")
        project_id = queries.insert_project(
            self.conn, "P-2842 — Lane Cove", project_number="P-2842")
        add_entry(self.conn, project_id)
        self.orphan = queries.insert_project(self.conn, "Admin", keywords="email")
        add_entry(self.conn, self.orphan, start_hour=14)

    def test_export_includes_sendable_entries_and_reports_the_rest(self):
        payloads, problems = ft.build_export_payloads(self.conn, TODAY, TODAY)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["project_number"], "P-2842")
        self.assertEqual(len(problems), 1)

    def test_export_ignores_push_state(self):
        ft.push_time_entries(self.conn, "k", TODAY, TODAY,
                             transport=RecordingTransport())
        payloads, _ = ft.build_export_payloads(self.conn, TODAY, TODAY)
        self.assertEqual(len(payloads), 1)

    def test_csv_has_the_five_columns_fieldflow_matches_on(self):
        import csv
        import io
        import tempfile
        import os
        from ui.reports.exporter import export_fieldflow_csv

        payloads, _ = ft.build_export_payloads(self.conn, TODAY, TODAY)
        path = os.path.join(tempfile.mkdtemp(), "ff.csv")
        export_fieldflow_csv(path, payloads)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        for column in ("external_id", "project_number", "person_email",
                       "started_at", "minutes"):
            self.assertTrue(rows[0][column], column)
        self.assertEqual(rows[0]["billable"], "true")


class MigrationTest(unittest.TestCase):

    def test_project_number_is_backfilled_from_legacy_keywords(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # A v4 database, as shipped by 0.3.x.
        conn.execute("""CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            client TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#4A90D9',
            keywords TEXT NOT NULL DEFAULT '', billable INTEGER NOT NULL DEFAULT 1,
            archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version (version) VALUES (4)")
        for name, keywords in [("P-2842 — Lane Cove", "P-2842"),
                               ("Admin", "email, invoices"),
                               ("Mystery", "")]:
            conn.execute(
                "INSERT INTO projects (name, keywords, created_at) VALUES (?, ?, ?)",
                (name, keywords, datetime.now().isoformat()),
            )
        conn.commit()

        init_schema(conn)

        numbers = {r["name"]: r["project_number"]
                   for r in conn.execute("SELECT name, project_number FROM projects")}
        self.assertEqual(numbers["P-2842 — Lane Cove"], "P-2842")
        self.assertEqual(numbers["Admin"], "")
        self.assertEqual(numbers["Mystery"], "")


if __name__ == "__main__":
    unittest.main()
