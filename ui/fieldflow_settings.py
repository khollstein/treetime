"""FieldFlow integration settings dialog."""

import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QSpinBox, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from database.queries import get_setting, set_setting
from integrations.fieldflow import (
    sync_projects, test_connection, DEFAULT_URL,
)


class FieldFlowSettingsDialog(QDialog):
    """Configure and run FieldFlow project sync."""

    sync_completed = Signal()  # emitted after a successful sync

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("FieldFlow Settings")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        header = QLabel("FieldFlow integration")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        sub = QLabel(
            "Pull project numbers from FieldFlow so Treetime can auto-assign "
            "tracked time to the right job."
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

    def _on_close(self):
        self._save()
        self.accept()
