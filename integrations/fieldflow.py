"""FieldFlow integration — sync projects from the Treetime cloud API."""

import json
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

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


def _find_match(projects, project_number: str):
    """Return a local Project whose name or keywords contain *project_number*."""
    pn_lower = project_number.lower()
    for p in projects:
        if pn_lower in p.name.lower():
            return p
        if pn_lower in (p.keywords or "").lower():
            return p
    return None


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
        project_number = rp.get("project_number", "")
        title = rp.get("title", "")
        client_name = rp.get("client_name", "")
        client_company = rp.get("client_company", "")
        keyword = rp.get("keyword", project_number)

        # Compose a display name: "ARB-001 — Tree Assessment - Smith Residence"
        display_name = f"{project_number} — {title}" if project_number and title else (title or project_number)
        client_display = client_company or client_name

        try:
            match = _find_match(local_projects, project_number)
            if match:
                # Update existing — preserve the user's chosen colour
                update_project(
                    conn,
                    match.id,
                    name=display_name,
                    client=client_display,
                    color=match.color,
                    keywords=keyword,
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
