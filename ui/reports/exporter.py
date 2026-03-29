"""CSV export for time reports."""

import csv
from datetime import date


def export_csv(filepath: str, report_data: list[dict],
               start_date: date, end_date: date):
    """Export report data to a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            f"Time Report: {start_date.isoformat()} to {end_date.isoformat()}"
        ])
        writer.writerow([])
        writer.writerow(["Project", "Client", "Hours"])

        total_hours = 0
        for row in report_data:
            total_hours += row["hours"]
            writer.writerow([
                row["name"],
                row["client"],
                f"{row['hours']:.2f}",
            ])

        writer.writerow([])
        writer.writerow(["TOTAL", "", f"{total_hours:.2f}"])
