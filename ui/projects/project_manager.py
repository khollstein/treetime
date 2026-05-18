"""Project management CRUD view."""

import sqlite3

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton,
    QDialog, QFormLayout, QLineEdit, QColorDialog, QCheckBox,
    QHeaderView, QAbstractItemView, QLabel,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QSortFilterProxyModel

from database import queries
from ui.projects.project_model import ProjectTableModel


class ProjectEditDialog(QDialog):
    """Add/edit a project."""

    def __init__(self, name="", client="", color="#4A90D9",
                 keywords="", billable=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)
        layout.setSpacing(12)

        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText("e.g. DA Report - 42 Elm St")
        layout.addRow("Project Name:", self._name_edit)

        self._client_edit = QLineEdit(client)
        self._client_edit.setPlaceholderText("e.g. North Sydney Council")
        layout.addRow("Client:", self._client_edit)

        self._color = color
        self._color_btn = QPushButton()
        self._color_btn.setStyleSheet(
            f"background-color: {color}; min-height: 30px; border: none; border-radius: 6px;"
        )
        self._color_btn.clicked.connect(self._pick_color)
        layout.addRow("Color:", self._color_btn)

        self._keywords_edit = QLineEdit(keywords)
        self._keywords_edit.setPlaceholderText("e.g. QGIS, council, elm street")
        keywords_help = QLabel(
            "Comma-separated. Matched against window titles to auto-suggest this project."
        )
        keywords_help.setWordWrap(True)
        keywords_help.setStyleSheet("font-size: 10px; color: #888; margin-top: -4px;")
        layout.addRow("Keywords:", self._keywords_edit)
        layout.addRow("", keywords_help)

        self._billable_check = QCheckBox("Billable")
        self._billable_check.setChecked(billable)
        billable_help = QLabel("Uncheck for non-billable tasks (admin, travel, internal)")
        billable_help.setStyleSheet("font-size: 10px; color: #888; margin-top: -4px;")
        layout.addRow("", self._billable_check)
        layout.addRow("", billable_help)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name()
            self._color_btn.setStyleSheet(
                f"background-color: {self._color}; min-height: 30px; border: none; border-radius: 6px;"
            )

    def _on_save(self):
        if self._name_edit.text().strip():
            self.accept()

    def result_data(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "client": self._client_edit.text().strip(),
            "color": self._color,
            "keywords": self._keywords_edit.text().strip(),
            "billable": self._billable_check.isChecked(),
        }


class ProjectManager(QWidget):
    """Project list with add/edit/archive controls."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("+ Add Project")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_project)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_project)
        archive_btn = QPushButton("Archive / Unarchive")
        archive_btn.clicked.connect(self._toggle_archive)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(archive_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Search bar
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search projects by name, client or keyword...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self._search_edit)

        # Table + proxy (for live filtering)
        self._model = ProjectTableModel(conn)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search across ALL columns

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(4, 70)  # Billable column
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._edit_project)
        layout.addWidget(self._table)

    def _on_search(self, text: str):
        self._proxy.setFilterFixedString(text)

    def _selected_project(self):
        """Return the Project for the currently selected table row, or None."""
        idx = self._table.currentIndex()
        if not idx.isValid():
            return None
        source_idx = self._proxy.mapToSource(idx)
        return self._model.get_project(source_idx.row())

    def _add_project(self):
        dlg = ProjectEditDialog(parent=self)
        if dlg.exec():
            data = dlg.result_data()
            queries.insert_project(
                self._conn, data["name"], data["client"],
                data["color"], data["keywords"], data["billable"],
            )
            self._model.refresh()

    def _edit_project(self):
        p = self._selected_project()
        if p is None:
            return
        dlg = ProjectEditDialog(
            name=p.name, client=p.client, color=p.color,
            keywords=p.keywords, billable=p.billable,
            parent=self,
        )
        if dlg.exec():
            data = dlg.result_data()
            queries.update_project(
                self._conn, p.id, data["name"], data["client"],
                data["color"], data["keywords"], data["billable"],
            )
            self._model.refresh()

    def _toggle_archive(self):
        p = self._selected_project()
        if p is None:
            return
        queries.archive_project(self._conn, p.id, not p.archived)
        self._model.refresh()
