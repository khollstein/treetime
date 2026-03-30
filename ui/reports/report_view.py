"""Reports view with date filtering and summary table."""

import sqlite3
from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog,
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor

from database import queries
from ui.reports.exporter import export_csv


class ReportView(QWidget):
    """Date-filtered report with hours by project and CSV export."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("From:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        today = date.today()
        self._start_date.setDate(QDate(today.year, today.month, 1))
        filter_layout.addWidget(self._start_date)

        filter_layout.addWidget(QLabel("To:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self._end_date)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primary")
        refresh_btn.clicked.connect(self._refresh)
        filter_layout.addWidget(refresh_btn)

        filter_layout.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        filter_layout.addWidget(export_btn)

        layout.addLayout(filter_layout)

        # Quick range buttons
        range_layout = QHBoxLayout()
        for label, days in [("This Week", 7), ("This Month", 30),
                            ("Last Month", -1), ("This Quarter", 90)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=days, l=label: self._set_range(d, l))
            range_layout.addWidget(btn)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # Summary table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Project", "Client", "Billable", "Hours"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Totals
        self._totals_label = QLabel()
        self._totals_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px;")
        layout.addWidget(self._totals_label)

        self._report_data = []
        self._refresh()

    def _get_start(self) -> date:
        d = self._start_date.date()
        return date(d.year(), d.month(), d.day())

    def _get_end(self) -> date:
        d = self._end_date.date()
        return date(d.year(), d.month(), d.day())

    def _set_range(self, days: int, label: str):
        today = date.today()
        if label == "Last Month":
            first_this_month = date(today.year, today.month, 1)
            last_month_end = first_this_month - timedelta(days=1)
            last_month_start = date(last_month_end.year, last_month_end.month, 1)
            self._start_date.setDate(QDate(last_month_start.year, last_month_start.month, last_month_start.day))
            self._end_date.setDate(QDate(last_month_end.year, last_month_end.month, last_month_end.day))
        else:
            start = today - timedelta(days=days)
            self._start_date.setDate(QDate(start.year, start.month, start.day))
            self._end_date.setDate(QDate.currentDate())
        self._refresh()

    def _refresh(self):
        start = self._get_start()
        end = self._get_end()
        self._report_data = queries.get_hours_by_project(self._conn, start, end)

        self._table.setRowCount(len(self._report_data))
        total_hours = 0
        billable_hours = 0
        non_billable_hours = 0

        for row_idx, row in enumerate(self._report_data):
            total_hours += row["hours"]
            is_billable = row.get("billable", True)
            if is_billable:
                billable_hours += row["hours"]
            else:
                non_billable_hours += row["hours"]

            name_item = QTableWidgetItem(row["name"])
            name_item.setBackground(QColor(row["color"]))
            name_item.setForeground(QColor("white"))
            self._table.setItem(row_idx, 0, name_item)
            self._table.setItem(row_idx, 1, QTableWidgetItem(row["client"]))

            billable_item = QTableWidgetItem("\u2713 Yes" if is_billable else "\u2014 No")
            billable_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row_idx, 2, billable_item)

            hours_item = QTableWidgetItem(f"{row['hours']:.2f}")
            hours_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, 3, hours_item)

        parts = [f"Total: {total_hours:.1f}h"]
        if billable_hours > 0:
            parts.append(f"Billable: {billable_hours:.1f}h")
        if non_billable_hours > 0:
            parts.append(f"Non-billable: {non_billable_hours:.1f}h")
        self._totals_label.setText("  |  ".join(parts))

    def _export_csv(self):
        if not self._report_data:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "time_report.csv",
            "CSV Files (*.csv)"
        )
        if filepath:
            export_csv(filepath, self._report_data,
                       self._get_start(), self._get_end())
