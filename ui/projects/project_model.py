"""Table model for the project list."""

import sqlite3

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor

from database import queries
from database.models import Project


COLUMNS = ["Name", "Client", "Color", "Keywords", "Status"]


class ProjectTableModel(QAbstractTableModel):

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._projects: list[Project] = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._projects = queries.get_all_projects(self._conn, include_archived=True)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._projects)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        p = self._projects[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return p.name
            if col == 1:
                return p.client
            if col == 2:
                return p.color
            if col == 3:
                return p.keywords
            if col == 4:
                return "Archived" if p.archived else "Active"

        if role == Qt.ItemDataRole.BackgroundRole and col == 2:
            return QColor(p.color)

        if role == Qt.ItemDataRole.ForegroundRole and col == 2:
            return QColor("white")

        return None

    def get_project(self, row: int) -> Project:
        return self._projects[row]
