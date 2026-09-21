"""Database schema creation and migrations."""

import re

SCHEMA_VERSION = 5

# Where finished time entries are pushed. The projects feed lives elsewhere
# (see integrations/fieldflow.py) but both use the same API key.
DEFAULT_TIME_ENDPOINT = (
    "https://fieldflow.canopyconsulting.com.au/functions/v1/treetime-time"
)

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
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        name           TEXT NOT NULL,
        client         TEXT NOT NULL DEFAULT '',
        color          TEXT NOT NULL DEFAULT '#4A90D9',
        keywords       TEXT NOT NULL DEFAULT '',
        project_number TEXT NOT NULL DEFAULT '',
        billable       INTEGER NOT NULL DEFAULT 1,
        archived       INTEGER NOT NULL DEFAULT 0,
        created_at     TEXT NOT NULL
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
    # Push state for FieldFlow. Keyed by time entry so a re-send is a no-op
    # on the receiving side, and kept after a local delete so the deletion
    # can be forwarded once.
    """CREATE TABLE IF NOT EXISTS time_entry_sync (
        entry_id     INTEGER PRIMARY KEY,
        external_id  TEXT NOT NULL,
        payload_hash TEXT NOT NULL DEFAULT '',
        status       TEXT NOT NULL DEFAULT 'pending',
        last_error   TEXT NOT NULL DEFAULT '',
        pushed_at    TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_time_entry_sync_status ON time_entry_sync(status)",
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

    # Block continuity — how forgiving auto-assign is about interruptions.
    "continuity_gap_s": "300",     # bridge unmatched/idle stretches up to 5 min
    "continuity_switch_s": "60",   # absorb a glance at another job up to 1 min
    "min_block_s": "60",           # ignore blocks shorter than a minute

    # FieldFlow time push
    "fieldflow_time_endpoint_url": DEFAULT_TIME_ENDPOINT,
    "fieldflow_person_email": "",
    "fieldflow_push_auto": "0",
    "fieldflow_push_hour": "19",
    "fieldflow_push_lookback_days": "7",
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

    if current_version < 5:
        try:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN project_number TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass
        _backfill_project_numbers(conn)
        conn.execute("UPDATE schema_version SET version = 5")


_PROJECT_NUMBER_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-_/ ]{1,23}$")


def _backfill_project_numbers(conn):
    """Recover project numbers from projects synced before v5.

    FieldFlow sync used to stash the project number in `keywords`, so a single
    keyword that looks like a job code is almost certainly one. Anything
    ambiguous is left blank for the next sync (or the user) to fill in.
    """
    try:
        rows = conn.execute(
            "SELECT id, name, keywords FROM projects WHERE project_number = ''"
        ).fetchall()
    except Exception:
        return
    for row in rows:
        keywords = (row["keywords"] or "").strip()
        if not keywords or "," in keywords:
            continue
        if not _PROJECT_NUMBER_RE.match(keywords):
            continue
        # A raw UUID row-key is not a project number.
        if len(keywords.replace("-", "")) >= 32:
            continue
        conn.execute(
            "UPDATE projects SET project_number = ? WHERE id = ?",
            (keywords, row["id"]),
        )
