"""Reports view — Summary and Timesheet modes."""

import sqlite3
from datetime import date, datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QComboBox, QStackedWidget, QFrame,
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont

from database import queries
from ui.reports.exporter import export_csv, export_timesheet_csv


class ReportView(QWidget):
    """Date-filtered report with Summary and Timesheet modes."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._mode = "summary"  # "summary" | "timesheet"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Mode toggle ───────────────────────────────────────────────
        mode_row = QHBoxLayout()

        self._summary_btn = QPushButton("Summary")
        self._summary_btn.setCheckable(True)
        self._summary_btn.setChecked(True)
        self._summary_btn.clicked.connect(lambda: self._set_mode("summary"))

        self._timesheet_btn = QPushButton("Timesheet")
        self._timesheet_btn.setCheckable(True)
        self._timesheet_btn.clicked.connect(lambda: self._set_mode("timesheet"))

        for btn in (self._summary_btn, self._timesheet_btn):
            btn.setFixedHeight(30)
            mode_row.addWidget(btn)

        mode_row.addSpacing(20)

        # Date range
        mode_row.addWidget(QLabel("From:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        today = date.today()
        self._start_date.setDate(QDate(today.year, today.month, 1))
        mode_row.addWidget(self._start_date)

        mode_row.addWidget(QLabel("To:"))
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        mode_row.addWidget(self._end_date)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primary")
        refresh_btn.clicked.connect(self._refresh)
        mode_row.addWidget(refresh_btn)

        mode_row.addStretch()

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.clicked.connect(self._export_csv)
        mode_row.addWidget(self._export_btn)

        layout.addLayout(mode_row)

        # ── Quick range buttons ───────────────────────────────────────
        range_layout = QHBoxLayout()
        for label, days in [("This Week", 7), ("This Month", 30),
                            ("Last Month", -1), ("This Quarter", 90)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=days, l=label: self._set_range(d, l))
            range_layout.addWidget(btn)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # ── Timesheet project filter (only visible in timesheet mode) ─
        self._filter_row = QWidget()
        filter_layout = QHBoxLayout(self._filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(QLabel("Project:"))
        self._project_combo = QComboBox()
        self._project_combo.setEditable(True)
        self._project_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._project_combo.lineEdit().setPlaceholderText("All projects")
        self._project_combo.setMinimumWidth(260)
        from PySide6.QtWidgets import QCompleter
        completer = self._project_combo.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._project_combo.currentIndexChanged.connect(self._refresh)
        filter_layout.addWidget(self._project_combo)
        filter_layout.addStretch()
        self._filter_row.setVisible(False)
        layout.addWidget(self._filter_row)

        # ── Stacked tables ────────────────────────────────────────────
        self._stack = QStackedWidget()

        # Page 0 — Summary
        self._summary_table = QTableWidget()
        self._summary_table.setColumnCount(4)
        self._summary_table.setHorizontalHeaderLabels(["Project", "Client", "Billable", "Hours"])
        self._summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._summary_table.setColumnWidth(2, 80)
        self._summary_table.setColumnWidth(3, 80)
        self._summary_table.setAlternatingRowColors(True)
        self._summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._summary_table.verticalHeader().setVisible(False)
        self._stack.addWidget(self._summary_table)

        # Page 1 — Timesheet
        self._timesheet_table = QTableWidget()
        self._timesheet_table.setColumnCount(7)
        self._timesheet_table.setHorizontalHeaderLabels(
            ["Date", "Day", "Project", "Start", "End", "Hours", "Note"]
        )
        hdr = self._timesheet_table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._timesheet_table.setColumnWidth(0, 95)
        self._timesheet_table.setColumnWidth(1, 80)
        self._timesheet_table.setColumnWidth(3, 58)
        self._timesheet_table.setColumnWidth(4, 58)
        self._timesheet_table.setColumnWidth(5, 58)
        self._timesheet_table.setAlternatingRowColors(True)
        self._timesheet_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._timesheet_table.verticalHeader().setVisible(False)
        self._stack.addWidget(self._timesheet_table)

        layout.addWidget(self._stack, 1)

        # ── Totals label ──────────────────────────────────────────────
        self._totals_label = QLabel()
        self._totals_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 6px 0;"
        )
        layout.addWidget(self._totals_label)

        self._summary_data = []
        self._timesheet_data = []

        self._populate_project_combo()
        self._refresh()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_start(self) -> date:
        d = self._start_date.date()
        return date(d.year(), d.month(), d.day())

    def _get_end(self) -> date:
        d = self._end_date.date()
        return date(d.year(), d.month(), d.day())

    def _set_range(self, days: int, label: str):
        today = date.today()
        if label == "Last Month":
            first = date(today.year, today.month, 1)
            end = first - timedelta(days=1)
            start = date(end.year, end.month, 1)
            self._start_date.setDate(QDate(start.year, start.month, start.day))
            self._end_date.setDate(QDate(end.year, end.month, end.day))
        else:
            start = today - timedelta(days=days)
            self._start_date.setDate(QDate(start.year, start.month, start.day))
            self._end_date.setDate(QDate.currentDate())
        self._refresh()

    def _set_mode(self, mode: str):
        self._mode = mode
        self._summary_btn.setChecked(mode == "summary")
        self._timesheet_btn.setChecked(mode == "timesheet")
        self._stack.setCurrentIndex(0 if mode == "summary" else 1)
        self._filter_row.setVisible(mode == "timesheet")
        self._refresh()

    def _populate_project_combo(self):
        self._project_combo.clear()
        self._project_combo.addItem("All projects", None)
        for p in queries.get_all_projects(self._conn):
            display = f"{p.name} ({p.client})" if p.client else p.name
            self._project_combo.addItem(display, p.id)

    def _selected_project_id(self):
        return self._project_combo.currentData()

    # ── Refresh ───────────────────────────────────────────────────────

    def _refresh(self):
        if self._mode == "summary":
            self._refresh_summary()
        else:
            self._refresh_timesheet()

    def _refresh_summary(self):
        start, end = self._get_start(), self._get_end()
        self._summary_data = queries.get_hours_by_project(self._conn, start, end)
        t = self._summary_table
        t.setRowCount(len(self._summary_data))

        total = billable = non_billable = 0.0
        for i, row in enumerate(self._summary_data):
            total += row["hours"]
            if row.get("billable", True):
                billable += row["hours"]
            else:
                non_billable += row["hours"]

            name_item = QTableWidgetItem(row["name"])
            name_item.setBackground(QColor(row["color"]))
            name_item.setForeground(QColor("white"))
            t.setItem(i, 0, name_item)
            t.setItem(i, 1, QTableWidgetItem(row["client"] or ""))

            bi = QTableWidgetItem("✓ Yes" if row.get("billable") else "— No")
            bi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(i, 2, bi)

            hi = QTableWidgetItem(f"{row['hours']:.2f}")
            hi.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(i, 3, hi)

        parts = [f"Total: {total:.1f}h"]
        if billable:
            parts.append(f"Billable: {billable:.1f}h")
        if non_billable:
            parts.append(f"Non-billable: {non_billable:.1f}h")
        self._totals_label.setText("  |  ".join(parts))

    def _refresh_timesheet(self):
        start, end = self._get_start(), self._get_end()
        pid = self._selected_project_id()
        self._timesheet_data = queries.get_timesheet_entries(
            self._conn, start, end, project_id=pid
        )
        t = self._timesheet_table
        t.setRowCount(len(self._timesheet_data))

        total = 0.0
        prev_date = None

        for i, row in enumerate(self._timesheet_data):
            total += row["hours"]
            is_new_date = row["entry_date"] != prev_date
            prev_date = row["entry_date"]

            # Bold the date cell when it changes to visually group entries by day
            date_item = QTableWidgetItem(row["entry_date"])
            if is_new_date:
                f = QFont()
                f.setBold(True)
                date_item.setFont(f)
            t.setItem(i, 0, date_item)

            t.setItem(i, 1, QTableWidgetItem(row["day_name"]))

            proj_item = QTableWidgetItem(row["name"])
            proj_item.setBackground(QColor(row["color"]))
            proj_item.setForeground(QColor("white"))
            t.setItem(i, 2, proj_item)

            # Format start/end as HH:MM
            try:
                st = datetime.fromisoformat(row["start_time"]).strftime("%H:%M")
                et = datetime.fromisoformat(row["end_time"]).strftime("%H:%M")
            except Exception:
                st = et = ""

            t.setItem(i, 3, QTableWidgetItem(st))
            t.setItem(i, 4, QTableWidgetItem(et))

            hi = QTableWidgetItem(f"{row['hours']:.2f}")
            hi.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(i, 5, hi)

            t.setItem(i, 6, QTableWidgetItem(row["note"]))

        count = len(self._timesheet_data)
        self._totals_label.setText(
            f"{count} entr{'y' if count == 1 else 'ies'}  |  Total: {total:.1f}h"
        )

    # ── Export ────────────────────────────────────────────────────────

    def _export_csv(self):
        start, end = self._get_start(), self._get_end()
        if self._mode == "summary":
            if not self._summary_data:
                return
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Export Summary CSV",
                f"summary_{start}_{end}.csv", "CSV Files (*.csv)"
            )
            if filepath:
                export_csv(filepath, self._summary_data, start, end)
        else:
            if not self._timesheet_data:
                return
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Export Timesheet CSV",
                f"timesheet_{start}_{end}.csv", "CSV Files (*.csv)"
            )
            if filepath:
                export_timesheet_csv(filepath, self._timesheet_data, start, end)
