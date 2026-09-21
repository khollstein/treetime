"""CSV export for time reports."""

import csv
from datetime import date, datetime


def export_csv(filepath: str, report_data: list[dict],
               start_date: date, end_date: date):
    """Export summary report (hours per project) to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            f"Time Report: {start_date.isoformat()} to {end_date.isoformat()}"
        ])
        writer.writerow([])
        writer.writerow(["Project", "Client", "Billable", "Hours"])

        total_hours = 0.0
        billable_hours = 0.0
        for row in report_data:
            total_hours += row["hours"]
            is_billable = row.get("billable", True)
            if is_billable:
                billable_hours += row["hours"]
            writer.writerow([
                row["name"],
                row["client"] or "",
                "Yes" if is_billable else "No",
                f"{row['hours']:.2f}",
            ])

        writer.writerow([])
        writer.writerow(["TOTAL", "", "", f"{total_hours:.2f}"])
        writer.writerow(["BILLABLE", "", "", f"{billable_hours:.2f}"])
        writer.writerow(["NON-BILLABLE", "", "", f"{total_hours - billable_hours:.2f}"])


def export_timesheet_csv(filepath: str, timesheet_data: list[dict],
                         start_date: date, end_date: date):
    """Export timesheet (one row per time entry) to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            f"Timesheet: {start_date.isoformat()} to {end_date.isoformat()}"
        ])
        writer.writerow([])
        writer.writerow([
            "Date", "Day", "Project", "Client", "Billable",
            "Start", "End", "Hours", "Note"
        ])

        total_hours = 0.0
        billable_hours = 0.0
        for row in timesheet_data:
            total_hours += row["hours"]
            is_billable = row.get("billable", True)
            if is_billable:
                billable_hours += row["hours"]

            try:
                st = datetime.fromisoformat(row["start_time"]).strftime("%H:%M")
                et = datetime.fromisoformat(row["end_time"]).strftime("%H:%M")
            except Exception:
                st = et = ""

            writer.writerow([
                row["entry_date"],
                row["day_name"],
                row["name"],
                row["client"] or "",
                "Yes" if is_billable else "No",
                st,
                et,
                f"{row['hours']:.2f}",
                row["note"] or "",
            ])

        writer.writerow([])
        writer.writerow(["TOTAL", "", "", "", "", "", "", f"{total_hours:.2f}", ""])
        writer.writerow(["BILLABLE", "", "", "", "", "", "", f"{billable_hours:.2f}", ""])
        writer.writerow(["NON-BILLABLE", "", "", "", "", "", "",
                         f"{total_hours - billable_hours:.2f}", ""])


def export_fieldflow_csv(filepath: str, payloads: list[dict]):
    """Export time entries in FieldFlow's upload shape.

    The fallback for when pushing isn't available: same fields, same matching
    on the FieldFlow side. One row per time entry, no totals — this is a data
    file, not a report.
    """
    columns = ["external_id", "project_number", "person_email",
               "started_at", "minutes", "description", "billable"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for payload in payloads:
            writer.writerow([
                payload.get("external_id", ""),
                payload.get("project_number", ""),
                payload.get("person_email", ""),
                payload.get("started_at", ""),
                payload.get("minutes", ""),
                payload.get("description", ""),
                "true" if payload.get("billable", True) else "false",
            ])
