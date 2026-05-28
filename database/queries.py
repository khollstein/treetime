"""Data access layer — all SQL wrapped in functions."""

import sqlite3
from datetime import datetime, date
from typing import Optional

from database.models import Activity, Project, TimeEntry

# Keep hourly_rate in queries for backwards compat with existing DBs
# but don't expose it in the UI


# ── Activities ──────────────────────────────────────────────────────

def insert_activity(conn: sqlite3.Connection, timestamp: datetime,
                    process: str, title: str, idle: bool, duration_s: int,
                    offline: bool = False) -> int:
    cur = conn.execute(
        "INSERT INTO activities (timestamp, process, title, idle, duration_s, offline) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp.isoformat(), process, title, int(idle), duration_s, int(offline)),
    )
    conn.commit()
    return cur.lastrowid


def update_activity_duration(conn: sqlite3.Connection, activity_id: int,
                             add_seconds: int):
    conn.execute(
        "UPDATE activities SET duration_s = duration_s + ? WHERE id = ?",
        (add_seconds, activity_id),
    )
    conn.commit()


def set_activity_duration(conn: sqlite3.Connection, activity_id: int,
                          duration_s: int):
    """Set the absolute duration of an activity (used for offline period updates)."""
    conn.execute(
        "UPDATE activities SET duration_s = ? WHERE id = ?",
        (duration_s, activity_id),
    )
    conn.commit()


def get_last_activity(conn: sqlite3.Connection) -> Optional[Activity]:
    row = conn.execute(
        "SELECT * FROM activities ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return Activity.from_row(row) if row else None


def get_activities_for_day(conn: sqlite3.Connection, day: date) -> list[Activity]:
    start = datetime(day.year, day.month, day.day, 0, 0, 0).isoformat()
    end = datetime(day.year, day.month, day.day, 23, 59, 59).isoformat()
    rows = conn.execute(
        "SELECT * FROM activities WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp",
        (start, end),
    ).fetchall()
    return [Activity.from_row(r) for r in rows]


def get_unassigned_offline_blocks(conn: sqlite3.Connection,
                                  day: date) -> list[Activity]:
    """Return offline activity blocks that are not dismissed and not
    covered by any existing time_entry (so the user can still assign them)."""
    start = datetime(day.year, day.month, day.day, 0, 0, 0).isoformat()
    end = datetime(day.year, day.month, day.day, 23, 59, 59).isoformat()
    # Backwards compat: older DBs may not have `dismissed` yet.
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM activities a
            WHERE a.timestamp BETWEEN ? AND ?
              AND a.offline = 1
              AND a.dismissed = 0
              AND NOT EXISTS (
                  SELECT 1 FROM time_entries t
                  WHERE t.start_time <= a.timestamp
                    AND t.end_time   >= datetime(a.timestamp,
                                                '+' || a.duration_s || ' seconds')
              )
            ORDER BY a.timestamp
            """,
            (start, end),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            """
            SELECT a.* FROM activities a
            WHERE a.timestamp BETWEEN ? AND ?
              AND a.offline = 1
              AND NOT EXISTS (
                  SELECT 1 FROM time_entries t
                  WHERE t.start_time <= a.timestamp
                    AND t.end_time   >= datetime(a.timestamp,
                                                '+' || a.duration_s || ' seconds')
              )
            ORDER BY a.timestamp
            """,
            (start, end),
        ).fetchall()
    return [Activity.from_row(r) for r in rows]


def dismiss_activity(conn: sqlite3.Connection, activity_id: int):
    """Mark an offline activity as dismissed so its banner stops appearing."""
    conn.execute(
        "UPDATE activities SET dismissed = 1 WHERE id = ?",
        (activity_id,),
    )
    conn.commit()


# ── Projects ────────────────────────────────────────────────────────

def insert_project(conn: sqlite3.Connection, name: str, client: str = "",
                   color: str = "#4A90D9", keywords: str = "",
                   billable: bool = True) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, client, color, keywords, billable, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, client, color, keywords, int(billable), datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def update_project(conn: sqlite3.Connection, project_id: int, name: str,
                   client: str, color: str, keywords: str = "",
                   billable: bool = True):
    conn.execute(
        "UPDATE projects SET name=?, client=?, color=?, keywords=?, billable=? WHERE id=?",
        (name, client, color, keywords, int(billable), project_id),
    )
    conn.commit()


def archive_project(conn: sqlite3.Connection, project_id: int, archived: bool = True):
    conn.execute(
        "UPDATE projects SET archived=? WHERE id=?",
        (int(archived), project_id),
    )
    conn.commit()


def get_all_projects(conn: sqlite3.Connection, include_archived: bool = False) -> list[Project]:
    if include_archived:
        rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects WHERE archived=0 ORDER BY name"
        ).fetchall()
    return [Project.from_row(r) for r in rows]


def get_project_by_id(conn: sqlite3.Connection, project_id: int) -> Optional[Project]:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return Project.from_row(row) if row else None


def match_project_by_keywords(conn: sqlite3.Connection,
                              process: str, title: str) -> Optional[Project]:
    """Find the best matching project based on keywords in process/title."""
    projects = get_all_projects(conn)
    search_text = f"{process} {title}".lower()

    best_match = None
    best_score = 0

    for p in projects:
        keywords = p.keyword_list()
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw in search_text)
        if score > best_score:
            best_score = score
            best_match = p

    return best_match


# ── Time Entries ────────────────────────────────────────────────────

def insert_time_entry(conn: sqlite3.Connection, project_id: int,
                      start_time: datetime, end_time: datetime,
                      note: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO time_entries (project_id, start_time, end_time, note, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, start_time.isoformat(), end_time.isoformat(), note,
         datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def update_time_entry(conn: sqlite3.Connection, entry_id: int,
                      project_id: int, start_time: datetime,
                      end_time: datetime, note: str):
    conn.execute(
        "UPDATE time_entries SET project_id=?, start_time=?, end_time=?, note=? "
        "WHERE id=?",
        (project_id, start_time.isoformat(), end_time.isoformat(), note, entry_id),
    )
    conn.commit()


def delete_time_entry(conn: sqlite3.Connection, entry_id: int):
    conn.execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
    conn.commit()


def get_time_entries_for_day(conn: sqlite3.Connection, day: date) -> list[TimeEntry]:
    start = datetime(day.year, day.month, day.day, 0, 0, 0).isoformat()
    end = datetime(day.year, day.month, day.day, 23, 59, 59).isoformat()
    rows = conn.execute(
        "SELECT * FROM time_entries "
        "WHERE start_time <= ? AND end_time >= ? "
        "ORDER BY start_time",
        (end, start),
    ).fetchall()
    return [TimeEntry.from_row(r) for r in rows]


def get_time_entries_for_range(conn: sqlite3.Connection,
                               start_date: date, end_date: date) -> list[TimeEntry]:
    start = datetime(start_date.year, start_date.month, start_date.day).isoformat()
    end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59).isoformat()
    rows = conn.execute(
        "SELECT * FROM time_entries "
        "WHERE start_time <= ? AND end_time >= ? "
        "ORDER BY start_time",
        (end, start),
    ).fetchall()
    return [TimeEntry.from_row(r) for r in rows]


def get_recent_project_ids(conn: sqlite3.Connection, limit: int = 5) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT project_id FROM time_entries "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["project_id"] for r in rows]


# ── Reports ─────────────────────────────────────────────────────────

def get_hours_by_project(conn: sqlite3.Connection,
                         start_date: date, end_date: date) -> list[dict]:
    start = datetime(start_date.year, start_date.month, start_date.day).isoformat()
    end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59).isoformat()
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.client, p.color, p.billable,
               SUM(
                   (julianday(MIN(te.end_time, ?)) - julianday(MAX(te.start_time, ?)))
                   * 24.0
               ) as hours
        FROM time_entries te
        JOIN projects p ON p.id = te.project_id
        WHERE te.start_time <= ? AND te.end_time >= ?
        GROUP BY p.id
        ORDER BY hours DESC
        """,
        (end, start, end, start),
    ).fetchall()
    return [
        {
            "project_id": r["id"],
            "name": r["name"],
            "client": r["client"],
            "color": r["color"],
            "billable": bool(r["billable"]),
            "hours": round(r["hours"], 2) if r["hours"] else 0,
        }
        for r in rows
    ]


def get_timesheet_entries(conn: sqlite3.Connection,
                          start_date: date, end_date: date,
                          project_id: int = None) -> list[dict]:
    """Return individual time entries within the range, joined with project info.

    Each row: date, day_name, project_id, name, client, color, billable,
               start_time, end_time, hours, note.
    Optionally filtered to a single project.
    """
    start = datetime(start_date.year, start_date.month, start_date.day).isoformat()
    end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59).isoformat()

    project_filter = "AND te.project_id = ?" if project_id else ""
    params = [end, start, end, start]
    if project_id:
        params.append(project_id)

    rows = conn.execute(
        f"""
        SELECT
            date(te.start_time)        AS entry_date,
            strftime('%A', te.start_time) AS day_name,
            p.id                       AS project_id,
            p.name, p.client, p.color, p.billable,
            te.start_time, te.end_time, te.note,
            (julianday(MIN(te.end_time, ?)) - julianday(MAX(te.start_time, ?)))
                * 24.0                 AS hours
        FROM time_entries te
        JOIN projects p ON p.id = te.project_id
        WHERE te.start_time <= ? AND te.end_time >= ?
        {project_filter}
        ORDER BY te.start_time
        """,
        params,
    ).fetchall()

    return [
        {
            "entry_date": r["entry_date"],
            "day_name":   r["day_name"],
            "project_id": r["project_id"],
            "name":       r["name"],
            "client":     r["client"] or "",
            "color":      r["color"],
            "billable":   bool(r["billable"]),
            "start_time": r["start_time"],
            "end_time":   r["end_time"],
            "hours":      round(max(r["hours"] or 0, 0), 2),
            "note":       r["note"] or "",
        }
        for r in rows
    ]


# ── Settings ────────────────────────────────────────────────────────

def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str):
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
