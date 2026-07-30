"""FieldFlow integration — sync projects from the Treetime cloud API."""

import json
import re
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

# Matches raw UUID row-keys that should never appear in a human-readable name.
# Covers: full UUIDs, UUIDs without dashes, and 8-char UUID fragments.
_ROW_KEY_RE = re.compile(
    r'^('
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    r'|[0-9a-f]{32}'
    r'|[0-9a-f]{8}'
    r')$',
    re.IGNORECASE,
)


def _is_row_key(s: str) -> bool:
    """Return True if *s* looks like a database row-ID, not a project code."""
    return bool(s) and bool(_ROW_KEY_RE.match(s))

from database.queries import get_all_projects, insert_project, update_project

DEFAULT_URL = "https://swpxgkbyeavjatjngkfz.supabase.co/functions/v1/treetime-projects"

# Rotating palette for auto-assigning colours to new projects
_AUTO_COLORS = [
    "#4C6EF5", "#E8644A", "#40C057", "#FAB005", "#9B59B6",
    "#1ABC9C", "#E67E22", "#3498DB", "#E74C3C", "#2ECC71",
    "#F39C12", "#8E44AD", "#16A085", "#D35400", "#2980B9",
]


def _next_color(existing_count: int) -> str:
    return _AUTO_COLORS[existing_count % len(_AUTO_COLORS)]


def _merge_keywords(existing: str, *new_keywords: str) -> str:
    """Merge keywords into an existing comma-separated list.

    User-added keywords are preserved; new ones are appended with
    case-insensitive de-duplication.
    """
    result = [k.strip() for k in (existing or "").split(",") if k.strip()]
    seen = {k.lower() for k in result}
    for kw_list in new_keywords:
        for kw in (kw_list or "").split(","):
            kw = kw.strip()
            if kw and kw.lower() not in seen:
                result.append(kw)
                seen.add(kw.lower())
    return ", ".join(result)


def _find_match(projects, project_number: str):
    """Return a local Project whose name or keywords contain *project_number*."""
    pn_lower = project_number.lower()
    for p in projects:
        if pn_lower in p.name.lower():
            return p
        if pn_lower in (p.keywords or "").lower():
            return p
    return None


def test_connection(api_key: str,
                    endpoint_url: str = DEFAULT_URL,
                    workspace_id: Optional[str] = None) -> tuple[bool, str]:
    """Quick GET against the endpoint to verify the key/URL.

    Returns ``(ok, message)``.
    """
    params: dict[str, str] = {"active_only": "true"}
    if workspace_id:
        params["workspace_id"] = workspace_id
    url = f"{endpoint_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        count = data.get("count", len(data.get("projects", [])))
        return True, f"Success — endpoint returned {count} project(s)."
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return False, f"HTTP {exc.code} {exc.reason}\n{body}".strip()
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"
    except json.JSONDecodeError as exc:
        return False, f"Bad JSON response: {exc}"
    except Exception as exc:
        return False, f"Unexpected error: {exc}"


def sync_projects(
    conn: sqlite3.Connection,
    api_key: str,
    endpoint_url: str = DEFAULT_URL,
    active_only: bool = True,
    workspace_id: Optional[str] = None,
) -> dict:
    """Fetch projects from FieldFlow and upsert into the local database.

    Returns ``{"created": int, "updated": int, "errors": list[str]}``.
    """
    created = 0
    updated = 0
    errors: list[str] = []

    # ── Build request ────────────────────────────────────────────────
    params: dict[str, str] = {"active_only": "true" if active_only else "false"}
    if workspace_id:
        params["workspace_id"] = workspace_id

    url = f"{endpoint_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-api-key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        errors.append(f"HTTP {exc.code}: {exc.reason}")
        return {"created": created, "updated": updated, "errors": errors}
    except urllib.error.URLError as exc:
        errors.append(f"Connection error: {exc.reason}")
        return {"created": created, "updated": updated, "errors": errors}
    except Exception as exc:
        errors.append(f"Unexpected error: {exc}")
        return {"created": created, "updated": updated, "errors": errors}

    remote_projects = data.get("projects", [])
    if not remote_projects:
        return {"created": created, "updated": updated, "errors": errors}

    # ── Upsert loop ──────────────────────────────────────────────────
    local_projects = get_all_projects(conn, include_archived=True)

    for rp in remote_projects:
        project_number = rp.get("project_number") or ""
        title = rp.get("title") or ""
        client_name = rp.get("client_name") or ""
        client_company = rp.get("client_company") or ""
        client_display = client_company or client_name or ""  # never None

        # If project_number is a raw UUID row-key, don't show it in the name.
        # Human-readable codes (e.g. "ARB-001", "P-2678") pass through fine.
        if project_number and not _is_row_key(project_number):
            display_name = f"{project_number} — {title}" if title else project_number
            # Always seed the project number as a keyword so window titles
            # containing it (e.g. "2026-03_E-002514_...") auto-match.
            keyword = _merge_keywords(rp.get("keyword") or "", project_number)
        else:
            # No readable code — use title only; fall back to UUID if truly empty
            display_name = title or project_number
            keyword = rp.get("keyword") or ""  # don't keyword-match on a UUID

        try:
            match = _find_match(local_projects, project_number)
            if match:
                # Update existing — preserve the user's chosen colour and
                # any keywords they added by hand
                update_project(
                    conn,
                    match.id,
                    name=display_name,
                    client=client_display,
                    color=match.color,
                    keywords=_merge_keywords(match.keywords, keyword),
                    billable=match.billable,
                )
                updated += 1
            else:
                # Create new project
                color = _next_color(len(local_projects) + created)
                insert_project(
                    conn,
                    name=display_name,
                    client=client_display,
                    color=color,
                    keywords=keyword,
                    billable=True,
                )
                created += 1
        except Exception as exc:
            errors.append(f"Error syncing {project_number}: {exc}")

    return {"created": created, "updated": updated, "errors": errors}
