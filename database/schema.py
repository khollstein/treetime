"""Database schema creation and migrations."""

SCHEMA_VERSION = 4

_TABLE_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS activities (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT NOT NULL,
        process     TEXT NOT NULL,
        title       TEXT NOT NULL,
        idle        INTEGER NOT NULL DEFAULT 0,
        duration_s  INTEGER NOT NULL DEFAULT 5,
        offline     INTEGER NOT NULL DEFAULT 0,
        dismissed   INTEGER NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_activities_ts ON activities(timestamp)",
    """CREATE TABLE IF NOT EXISTS projects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        client      TEXT NOT NULL DEFAULT '',
        color       TEXT NOT NULL DEFAULT '#4A90D9',
        keywords    TEXT NOT NULL DEFAULT '',
        billable    INTEGER NOT NULL DEFAULT 1,
        archived    INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS time_entries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER NOT NULL REFERENCES projects(id),
        start_time  TEXT NOT NULL,
        end_time    TEXT NOT NULL,
        note        TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_time_entries_range ON time_entries(start_time, end_time)",
    """CREATE TABLE IF NOT EXISTS app_settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )""",
]

DEFAULT_SETTINGS = {
    "poll_interval_ms": "5000",
    "idle_threshold_s": "300",
    "theme": "dark",
    "capture_titles": "full",  # "full" or "process_only"
}


def init_schema(conn):
    """Create tables and seed defaults if needed."""
    for stmt in _TABLE_STATEMENTS:
        conn.execute(stmt)
    conn.commit()

    # Check if schema_version has a row
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    else:
        _run_migrations(conn, row["version"])

    # Seed default settings (don't overwrite existing)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    conn.commit()


def _run_migrations(conn, current_version: int):
    """Run incremental migrations."""
    if current_version < 2:
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN keywords TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        conn.execute("UPDATE schema_version SET version = 2")

    if current_version < 3:
        try:
            conn.execute("ALTER TABLE activities ADD COLUMN offline INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN billable INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass
        conn.execute("UPDATE schema_version SET version = 3")

    if current_version < 4:
        try:
            conn.execute("ALTER TABLE activities ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        conn.execute("UPDATE schema_version SET version = 4")
