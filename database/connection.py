"""SQLite connection factory with WAL mode."""

import os
import re
import sqlite3
from datetime import date

from config import DATA_DIR, DB_PATH
from database.schema import init_schema

_BACKUP_NAME_RE = re.compile(r"^data-\d{4}-\d{2}-\d{2}\.db$")


def get_connection() -> sqlite3.Connection:
    """Create or return a connection to the app database."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    init_schema(conn)
    _backup_daily(conn)
    return conn


def _backup_daily(conn: sqlite3.Connection, keep: int = 14):
    """Snapshot the database to backups/data-YYYY-MM-DD.db once per day.

    Uses the SQLite online backup API (safe with WAL). Keeps the most
    recent `keep` snapshots. A failed backup must never block startup.
    """
    try:
        backups_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(backups_dir, exist_ok=True)

        dest_path = os.path.join(backups_dir, f"data-{date.today().isoformat()}.db")
        if not os.path.exists(dest_path):
            dest = sqlite3.connect(dest_path)
            try:
                conn.backup(dest)
            finally:
                dest.close()

        backups = sorted(f for f in os.listdir(backups_dir)
                         if _BACKUP_NAME_RE.match(f))
        for old in backups[:-keep]:
            os.remove(os.path.join(backups_dir, old))
    except Exception:
        pass
