"""FieldFlow integration settings dialog."""

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QSpinBox, QFrame, QMessageBox, QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication

from database.queries import get_push_status_counts, get_setting, set_setting
from integrations.fieldflow import (
    sync_projects, test_connection, DEFAULT_URL,
)
from integrations import fieldflow_time


def format_push_result(result: dict) -> str:
    """Plain-English summary of a push, including what did not go."""
    lines = [
        f"Sent {result['sent']} entr{'y' if result['sent'] == 1 else 'ies'} "
        f"to FieldFlow."
    ]
    if result.get("skipped"):
        lines.append(f"{result['skipped']} already up to date.")
    if result.get("deleted"):
        lines.append(f"{result['deleted']} withdrawn after being deleted here.")
    if result.get("failed"):
        lines.append(f"{result['failed']} could not be sent — they will be "
                     f"retried on the next push.")

    problems = result.get("problems") or []
    if problems:
        lines.append("")
        lines.append("Not sent:")
        lines.extend(f"  \u2022 {p}" for p in problems[:10])
        if len(problems) > 10:
            lines.append(f"  \u2022 ...and {len(problems) - 10} more")

    errors = result.get("errors") or []
    if errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  \u2022 {e}" for e in errors[:5])
    return "\n".join(lines)


def show_push_result(parent, result: dict):
    """Report a push to the user — a warning only if something went wrong."""
    text = format_push_result(result)
    if result.get("errors") or result.get("failed"):
        QMessageBox.warning(parent, "Push finished with problems", text)
    else:
        QMessageBox.information(parent, "Push complete", text)


class FieldFlowSettingsDialog(QDialog):
    """Configure and run FieldFlow project sync."""

    sync_completed = Signal()  # emitted after a successful sync

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("FieldFlow Settings")
        self.setMinimumWidth(560)

        # Both halves of the integration live here, which is more than fits
        # on a short laptop screen — so the body scrolls.
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        header = QLabel("FieldFlow integration")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        sub = QLabel(
            "Pull project numbers down from FieldFlow so Treetime can auto-assign "
            "tracked time to the right job, and push the finished time back up."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888;")
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # Form
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # API key (with show/hide)
        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        self._key_edit = QLineEdit(get_setting(conn, "fieldflow_api_key", ""))
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("Paste your FieldFlow API key")
        self._show_key_btn = QPushButton("Show")
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.setFixedWidth(60)
        self._show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._key_edit, 1)
        key_row.addWidget(self._show_key_btn)
        key_w = QFrame()
        key_w.setLayout(key_row)
        form.addRow("API key:", key_w)

        # Endpoint URL
        self._url_edit = QLineEdit(get_setting(conn, "fieldflow_endpoint_url", DEFAULT_URL))
        self._url_edit.setPlaceholderText(DEFAULT_URL)
        form.addRow("Endpoint URL:", self._url_edit)

        # Workspace ID (optional)
        self._workspace_edit = QLineEdit(get_setting(conn, "fieldflow_workspace_id", ""))
        self._workspace_edit.setPlaceholderText("Optional — leave blank to sync all workspaces")
        form.addRow("Workspace ID:", self._workspace_edit)

        # Auto-sync
        auto_row = QHBoxLayout()
        self._auto_check = QCheckBox("Auto-sync every")
        self._auto_check.setChecked(
            int(get_setting(conn, "fieldflow_auto_sync_hours", "0") or "0") > 0
        )
        self._auto_spin = QSpinBox()
        self._auto_spin.setRange(1, 24)
        self._auto_spin.setValue(
            max(1, int(get_setting(conn, "fieldflow_auto_sync_hours", "6") or "6"))
        )
        self._auto_spin.setSuffix(" hours")
        auto_row.addWidget(self._auto_check)
        auto_row.addWidget(self._auto_spin)
        auto_row.addStretch()
        auto_w = QFrame()
        auto_w.setLayout(auto_row)
        form.addRow("", auto_w)

        layout.addLayout(form)

        # ── Time push ────────────────────────────────────────────────
        push_line = QFrame()
        push_line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(push_line)

        push_header = QLabel("Push time to FieldFlow")
        push_header.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(push_header)

        push_sub = QLabel(
            "Finished time entries are sent to FieldFlow and land in its review "
            "list. Each entry carries a stable id, so re-sending the same day "
            "updates what is already there instead of duplicating it. Entries "
            "need a project number and your Canopy email to be matched."
        )
        push_sub.setWordWrap(True)
        push_sub.setStyleSheet("color: #888;")
        layout.addWidget(push_sub)

        push_form = QFormLayout()
        push_form.setSpacing(8)
        push_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._email_edit = QLineEdit(get_setting(conn, "fieldflow_person_email", ""))
        self._email_edit.setPlaceholderText("you@canopyconsulting.com.au")
        push_form.addRow("Your email:", self._email_edit)

        self._time_url_edit = QLineEdit(
            get_setting(conn, "fieldflow_time_endpoint_url",
                        fieldflow_time.DEFAULT_URL)
        )
        self._time_url_edit.setPlaceholderText(fieldflow_time.DEFAULT_URL)
        push_form.addRow("Time endpoint:", self._time_url_edit)

        push_row = QHBoxLayout()
        self._push_auto_check = QCheckBox("Push automatically at")
        self._push_auto_check.setChecked(
            get_setting(conn, "fieldflow_push_auto", "0") == "1"
        )
        self._push_hour_spin = QSpinBox()
        self._push_hour_spin.setRange(0, 23)
        self._push_hour_spin.setSuffix(":00")
        self._push_hour_spin.setValue(self._int_setting("fieldflow_push_hour", 19, 0, 23))
        self._push_days_spin = QSpinBox()
        self._push_days_spin.setRange(1, 60)
        self._push_days_spin.setSuffix(" days")
        self._push_days_spin.setValue(
            self._int_setting("fieldflow_push_lookback_days", 7, 1, 60)
        )
        push_row.addWidget(self._push_auto_check)
        push_row.addWidget(self._push_hour_spin)
        push_row.addWidget(QLabel("covering the last"))
        push_row.addWidget(self._push_days_spin)
        push_row.addStretch()
        push_w = QFrame()
        push_w.setLayout(push_row)
        push_form.addRow("", push_w)

        layout.addLayout(push_form)

        self._push_status_label = QLabel()
        self._push_status_label.setStyleSheet("color: #888; font-size: 11px;")
        self._refresh_push_status()
        layout.addWidget(self._push_status_label)

        push_btn_row = QHBoxLayout()
        push_btn_row.setSpacing(6)
        self._push_test_btn = QPushButton("Test Time Endpoint")
        self._push_test_btn.clicked.connect(self._on_test_push)
        self._push_btn = QPushButton("Push Time Now")
        self._push_btn.clicked.connect(self._on_push)
        push_btn_row.addWidget(self._push_test_btn)
        push_btn_row.addWidget(self._push_btn)
        push_btn_row.addStretch()
        layout.addLayout(push_btn_row)

        sync_line = QFrame()
        sync_line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sync_line)

        # Last sync status
        last = get_setting(conn, "fieldflow_last_sync", "")
        self._status_label = QLabel(
            f"Last sync: <b>{last or 'never'}</b>"
        )
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        self._test_btn = QPushButton("Test Connection")
        self._test_btn.clicked.connect(self._on_test)

        self._sync_btn = QPushButton("Sync Now")
        self._sync_btn.setObjectName("primary")
        self._sync_btn.clicked.connect(self._on_sync)

        action_row.addWidget(self._test_btn)
        action_row.addWidget(self._sync_btn)
        action_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._on_close)
        action_row.addWidget(close_btn)

        layout.addLayout(action_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen else 800
        self.resize(600, min(content.sizeHint().height() + 8,
                             int(available * 0.9)))

    def _int_setting(self, key: str, default: int, low: int, high: int) -> int:
        try:
            value = int(get_setting(self._conn, key, str(default)) or default)
        except (TypeError, ValueError):
            value = default
        return max(low, min(high, value))

    def _refresh_push_status(self):
        last = get_setting(self._conn, "fieldflow_last_push", "")
        counts = get_push_status_counts(self._conn)
        parts = [f"Last push: <b>{last or 'never'}</b>"]
        if counts.get("error"):
            parts.append(f"{counts['error']} entr"
                         f"{'y' if counts['error'] == 1 else 'ies'} failed")
        if counts.get("pending_delete"):
            parts.append(f"{counts['pending_delete']} deletion(s) queued")
        self._push_status_label.setText("  |  ".join(parts))

    def _toggle_key_visibility(self, shown: bool):
        self._key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self._show_key_btn.setText("Hide" if shown else "Show")

    def _save(self):
        """Persist all visible fields to app_settings."""
        set_setting(self._conn, "fieldflow_api_key", self._key_edit.text().strip())
        set_setting(self._conn, "fieldflow_endpoint_url",
                    self._url_edit.text().strip() or DEFAULT_URL)
        set_setting(self._conn, "fieldflow_workspace_id",
                    self._workspace_edit.text().strip())
        hours = self._auto_spin.value() if self._auto_check.isChecked() else 0
        set_setting(self._conn, "fieldflow_auto_sync_hours", str(hours))

        set_setting(self._conn, "fieldflow_person_email",
                    self._email_edit.text().strip())
        set_setting(self._conn, "fieldflow_time_endpoint_url",
                    self._time_url_edit.text().strip() or fieldflow_time.DEFAULT_URL)
        set_setting(self._conn, "fieldflow_push_auto",
                    "1" if self._push_auto_check.isChecked() else "0")
        set_setting(self._conn, "fieldflow_push_hour",
                    str(self._push_hour_spin.value()))
        set_setting(self._conn, "fieldflow_push_lookback_days",
                    str(self._push_days_spin.value()))

    def _current_inputs(self) -> tuple[str, str, str]:
        return (
            self._key_edit.text().strip(),
            self._url_edit.text().strip() or DEFAULT_URL,
            self._workspace_edit.text().strip(),
        )

    def _on_test(self):
        key, url, workspace = self._current_inputs()
        if not key:
            QMessageBox.warning(self, "API key required",
                                "Enter your FieldFlow API key before testing.")
            return
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing...")
        try:
            ok, msg = test_connection(key, url, workspace or None)
        finally:
            self._test_btn.setEnabled(True)
            self._test_btn.setText("Test Connection")
        if ok:
            QMessageBox.information(self, "Connection OK", msg)
        else:
            QMessageBox.warning(self, "Connection failed", msg)

    def _on_sync(self):
        key, url, workspace = self._current_inputs()
        if not key:
            QMessageBox.warning(self, "API key required",
                                "Enter your FieldFlow API key before syncing.")
            return
        self._save()  # save before sync so prefs persist if app crashes
        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Syncing...")
        try:
            result = sync_projects(
                self._conn,
                api_key=key,
                endpoint_url=url,
                workspace_id=workspace or None,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Sync error", f"Unexpected error:\n{exc}")
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("Sync Now")
            return
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("Sync Now")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        set_setting(self._conn, "fieldflow_last_sync", now_str)
        self._status_label.setText(f"Last sync: <b>{now_str}</b>")

        if result["errors"]:
            QMessageBox.warning(
                self, "Sync finished with errors",
                f"Created {result['created']} project(s), "
                f"updated {result['updated']} project(s).\n\n"
                f"Errors:\n" + "\n".join(result["errors"]),
            )
        else:
            QMessageBox.information(
                self, "Sync complete",
                f"Created {result['created']} project(s), "
                f"updated {result['updated']} project(s).",
            )

        self.sync_completed.emit()

    # ── Time push ────────────────────────────────────────────────────

    def _on_test_push(self):
        key = self._key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "API key required",
                                "Enter your FieldFlow API key before testing.")
            return
        url = self._time_url_edit.text().strip() or fieldflow_time.DEFAULT_URL
        self._push_test_btn.setEnabled(False)
        self._push_test_btn.setText("Testing...")
        try:
            ok, msg = fieldflow_time.test_connection(key, url)
        finally:
            self._push_test_btn.setEnabled(True)
            self._push_test_btn.setText("Test Time Endpoint")
        if ok:
            QMessageBox.information(self, "Time endpoint OK", msg)
        else:
            QMessageBox.warning(self, "Time endpoint failed", msg)

    def _on_push(self):
        key = self._key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "API key required",
                                "Enter your FieldFlow API key before pushing.")
            return
        if not self._email_edit.text().strip():
            QMessageBox.warning(
                self, "Email required",
                "Enter the Canopy email your time should land against.")
            return
        self._save()

        self._push_btn.setEnabled(False)
        self._push_btn.setText("Pushing...")
        try:
            result = fieldflow_time.push_recent(
                self._conn,
                api_key=key,
                lookback_days=self._push_days_spin.value(),
                endpoint_url=self._time_url_edit.text().strip()
                             or fieldflow_time.DEFAULT_URL,
                person_email=self._email_edit.text().strip(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Push error", f"Unexpected error:\n{exc}")
            return
        finally:
            self._push_btn.setEnabled(True)
            self._push_btn.setText("Push Time Now")

        now = datetime.now()
        set_setting(self._conn, "fieldflow_last_push",
                    now.strftime("%Y-%m-%d %H:%M:%S"))
        if not result["errors"]:
            # Lets the nightly batch know today is covered.
            set_setting(self._conn, "fieldflow_last_push_date",
                        now.date().isoformat())
        self._refresh_push_status()
        show_push_result(self, result)

    def _on_close(self):
        self._save()
        self.accept()
