"""SQLite connection factory with WAL mode."""

import os
import sqlite3

from config import DATA_DIR, DB_PATH
from database.schema import init_schema


def get_connection() -> sqlite3.Connection:
    """Create or return a connection to the app database."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn
