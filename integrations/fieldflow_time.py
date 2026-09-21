"""FieldFlow integration — push finished time entries up to FieldFlow.

The projects feed (integrations/fieldflow.py) pulls job codes down; this pushes
time back the other way, against the same API key.

Entries land in a review list on the FieldFlow side, so the contract is
deliberately small — see docs/fieldflow-time-contract.md:

    POST <endpoint>            x-api-key: <the Treetime key>
    { "entries": [ { external_id, project_number, person_email,
                     started_at, minutes, description, billable } ] }

``external_id`` is what makes a resend safe: it is stable for the life of a
time entry, so sending the same batch twice updates rather than duplicates.
That is why nothing here is fire-and-forget — every attempt is written to
`time_entry_sync`, and only entries that are new or have actually changed go
out again.
"""

import hashlib
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from database import queries
from database.models import Project
from database.schema import DEFAULT_TIME_ENDPOINT

DEFAULT_URL = DEFAULT_TIME_ENDPOINT

# One POST per this many entries. A day of work is a handful of entries, so
# this only matters for the first push after a long gap.
BATCH_SIZE = 200

REQUEST_TIMEOUT_S = 30


# ── Identity ────────────────────────────────────────────────────────

def get_install_id(conn: sqlite3.Connection) -> str:
    """A stable id for this Treetime install.

    Entry ids restart at 1 on a fresh database, so they are not unique across
    machines. Prefixing with an install id keeps `external_id` globally unique
    without FieldFlow needing to know anything about who is sending.
    """
    install_id = queries.get_setting(conn, "install_id", "")
    if not install_id:
        install_id = uuid.uuid4().hex[:8]
        queries.set_setting(conn, "install_id", install_id)
    return install_id


def external_id_for(install_id: str, entry_id: int) -> str:
    return f"tt-{install_id}-{entry_id}"


# ── Payload building ────────────────────────────────────────────────

def _project_number_for_row(row: dict) -> str:
    """Job code for a push row, reusing the model's resolution rules."""
    project = Project(
        id=row.get("project_id") or 0,
        name=row.get("name") or "",
        client=row.get("client") or "",
        color="",
        keywords=row.get("keywords") or "",
        billable=bool(row.get("billable", True)),
        archived=False,
        created_at=datetime.now(),
        project_number=row.get("project_number") or "",
    )
    return project.resolved_project_number()


def _local_isoformat(value) -> str:
    """ISO 8601 with the machine's UTC offset, which FieldFlow requires."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive timestamps are local time
    return dt.isoformat()


def build_entry_payload(row: dict, person_email: str,
                        install_id: str) -> tuple[Optional[dict], Optional[str]]:
    """Turn a push row into one entry, or explain why it can't be sent."""
    start = datetime.fromisoformat(row["start_time"])
    end = datetime.fromisoformat(row["end_time"])
    minutes = int(round((end - start).total_seconds() / 60.0))

    project_number = _project_number_for_row(row)
    if not project_number:
        return None, (
            f"{row.get('name') or 'project'}: no project number — "
            "set one on the project or re-sync from FieldFlow"
        )
    if not person_email:
        return None, "no person email configured"
    if minutes <= 0:
        return None, f"{row.get('name') or 'entry'}: shorter than a minute"

    payload = {
        "external_id": external_id_for(install_id, row["id"]),
        "project_number": project_number,
        "person_email": person_email,
        "started_at": _local_isoformat(start),
        "minutes": minutes,
        "description": (row.get("note") or "").strip(),
        "billable": bool(row.get("billable", True)),
        # Optional context for the review screen; FieldFlow may ignore these.
        "project_name": row.get("name") or "",
        "client": row.get("client") or "",
    }
    return payload, None


def payload_hash(payload: dict) -> str:
    """Fingerprint of what was sent, so unchanged entries are not resent."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_push_set(conn: sqlite3.Connection, start_date: date, end_date: date,
                   person_email: str, install_id: str,
                   force: bool = False) -> dict:
    """Work out exactly what should go over the wire.

    Returns ``{"entries": [...], "skipped": int, "problems": [str]}`` where
    each entry is ``{"payload": dict, "entry_id": int, "hash": str}``.
    """
    entries: list[dict] = []
    problems: list[str] = []
    skipped = 0

    for row in queries.get_entries_for_push(conn, start_date, end_date):
        payload, problem = build_entry_payload(row, person_email, install_id)
        if payload is None:
            # One missing setting can fail every entry; say it once.
            if problem not in problems:
                problems.append(problem)
            continue
        digest = payload_hash(payload)
        unchanged = (row.get("status") == "sent"
                     and row.get("payload_hash") == digest)
        if unchanged and not force:
            skipped += 1
            continue
        entries.append({"payload": payload, "entry_id": row["id"], "hash": digest})

    # Entries deleted locally after FieldFlow already had them.
    for deletion in queries.get_pending_deletions(conn):
        entries.append({
            "payload": {"external_id": deletion["external_id"], "deleted": True},
            "entry_id": deletion["entry_id"],
            "hash": "",
            "deletion": True,
        })

    return {"entries": entries, "skipped": skipped, "problems": problems}


# ── HTTP ────────────────────────────────────────────────────────────

def _default_transport(url: str, api_key: str, body: bytes) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("x-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _post_batch(url: str, api_key: str, payloads: list[dict],
                transport: Callable) -> tuple[bool, str, dict]:
    """POST one batch. Returns ``(ok, message, parsed_body)``."""
    body = json.dumps({"entries": payloads}).encode("utf-8")
    try:
        status, text = transport(url, api_key, body)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return False, f"HTTP {exc.code} {exc.reason} {detail}".strip(), {}
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}", {}
    except Exception as exc:
        return False, f"Unexpected error: {exc}", {}

    if not 200 <= status < 300:
        return False, f"HTTP {status}: {text[:200]}".strip(), {}

    try:
        parsed = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        parsed = {}
    return True, "", parsed if isinstance(parsed, dict) else {}


def _rejections_by_external_id(parsed: dict) -> dict:
    """Pull per-entry rejections out of a response, if it reports any.

    The endpoint is free to answer with nothing but a 2xx; if it does report
    per-entry results, honour them so a rejected entry is retried next time.
    """
    rejected: dict[str, str] = {}
    results = parsed.get("results")
    if not isinstance(results, list):
        return rejected
    for item in results:
        if not isinstance(item, dict):
            continue
        external_id = item.get("external_id")
        status = (item.get("status") or "").lower()
        if not external_id:
            continue
        if status in ("rejected", "error", "failed", "unmatched", "invalid"):
            rejected[external_id] = str(
                item.get("reason") or item.get("error") or status
            )
    return rejected


# ── Entry point ─────────────────────────────────────────────────────

def push_time_entries(conn: sqlite3.Connection, api_key: str,
                      start_date: date, end_date: date,
                      endpoint_url: str = DEFAULT_URL,
                      person_email: str = "",
                      force: bool = False,
                      transport: Callable = None) -> dict:
    """Push time entries for the date range to FieldFlow.

    Returns ``{"sent", "skipped", "deleted", "failed", "problems", "errors"}``.
    Nothing is marked as sent unless the endpoint accepted it.
    """
    transport = transport or _default_transport
    result = {"sent": 0, "skipped": 0, "deleted": 0, "failed": 0,
              "problems": [], "errors": []}

    if not api_key:
        result["errors"].append("No FieldFlow API key configured.")
        return result

    person_email = (person_email
                    or queries.get_setting(conn, "fieldflow_person_email", "")).strip()
    install_id = get_install_id(conn)

    push_set = build_push_set(conn, start_date, end_date, person_email,
                              install_id, force=force)
    result["skipped"] = push_set["skipped"]
    result["problems"] = push_set["problems"]

    items = push_set["entries"]
    if not items:
        return result

    url = endpoint_url or DEFAULT_URL
    for offset in range(0, len(items), BATCH_SIZE):
        batch = items[offset:offset + BATCH_SIZE]
        ok, message, parsed = _post_batch(
            url, api_key, [i["payload"] for i in batch], transport
        )

        if not ok:
            result["errors"].append(message)
            result["failed"] += len(batch)
            for item in batch:
                if item.get("deletion"):
                    continue
                queries.record_push_attempt(
                    conn, item["entry_id"], item["payload"]["external_id"],
                    item["hash"], "error", message[:300],
                )
            continue

        rejected = _rejections_by_external_id(parsed)
        for item in batch:
            external_id = item["payload"]["external_id"]
            reason = rejected.get(external_id)
            if reason:
                result["failed"] += 1
                result["problems"].append(f"{external_id}: {reason}")
                if not item.get("deletion"):
                    queries.record_push_attempt(
                        conn, item["entry_id"], external_id, item["hash"],
                        "error", reason[:300],
                    )
                continue
            if item.get("deletion"):
                queries.clear_deletion(conn, item["entry_id"])
                result["deleted"] += 1
            else:
                queries.record_push_attempt(
                    conn, item["entry_id"], external_id, item["hash"], "sent",
                )
                result["sent"] += 1

    return result


def push_recent(conn: sqlite3.Connection, api_key: str, lookback_days: int = 7,
                endpoint_url: str = DEFAULT_URL, person_email: str = "",
                today: Optional[date] = None, transport: Callable = None) -> dict:
    """Push the last *lookback_days* days — what the nightly batch sends."""
    today = today or date.today()
    start = today - timedelta(days=max(0, lookback_days - 1))
    return push_time_entries(conn, api_key, start, today,
                             endpoint_url=endpoint_url,
                             person_email=person_email,
                             transport=transport)


def build_export_payloads(conn: sqlite3.Connection, start_date: date,
                          end_date: date,
                          person_email: str = "") -> tuple[list, list]:
    """Entries for the range as payload dicts, for the CSV fallback.

    FieldFlow can take a file upload instead of a push; the columns are the
    same fields a push sends, so both routes land in the same review screen.
    Ignores push state — an export is a snapshot, not a delta.
    """
    person_email = (person_email
                    or queries.get_setting(conn, "fieldflow_person_email", "")).strip()
    push_set = build_push_set(conn, start_date, end_date, person_email,
                              get_install_id(conn), force=True)
    payloads = [item["payload"] for item in push_set["entries"]
                if not item.get("deletion")]
    return payloads, push_set["problems"]


def test_connection(api_key: str, endpoint_url: str = DEFAULT_URL,
                    transport: Callable = None) -> tuple[bool, str]:
    """POST an empty batch to check the key and URL before a real push."""
    transport = transport or _default_transport
    ok, message, parsed = _post_batch(endpoint_url or DEFAULT_URL, api_key,
                                      [], transport)
    if ok:
        return True, "Success — the endpoint accepted an empty batch."
    return False, message
