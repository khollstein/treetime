"""Dataclass representations of database rows."""

import re
from dataclasses import dataclass
from datetime import datetime


def _looks_like_code(text: str) -> bool:
    """True if *text* could be a job code — short, has a digit, no spaces."""
    text = (text or "").strip()
    if not (2 <= len(text) <= 24) or " " in text:
        return False
    if not any(c.isdigit() for c in text):
        return False
    # A raw UUID row-key is not a job code.
    return len(text.replace("-", "")) < 32


@dataclass
class Activity:
    id: int
    timestamp: datetime
    process: str
    title: str
    idle: bool
    duration_s: int
    offline: bool = False
    dismissed: bool = False

    @classmethod
    def from_row(cls, row) -> "Activity":
        try:
            offline = bool(row["offline"])
        except (IndexError, KeyError):
            offline = False
        try:
            dismissed = bool(row["dismissed"])
        except (IndexError, KeyError):
            dismissed = False
        return cls(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            process=row["process"],
            title=row["title"],
            idle=bool(row["idle"]),
            duration_s=row["duration_s"],
            offline=offline,
            dismissed=dismissed,
        )


@dataclass
class Project:
    id: int
    name: str
    client: str
    color: str
    keywords: str
    billable: bool
    archived: bool
    created_at: datetime
    project_number: str = ""

    @classmethod
    def from_row(cls, row) -> "Project":
        # Handle older DBs without keywords/billable columns
        try:
            keywords = row["keywords"]
        except (IndexError, KeyError):
            keywords = ""
        try:
            billable = bool(row["billable"])
        except (IndexError, KeyError):
            billable = True
        try:
            project_number = row["project_number"]
        except (IndexError, KeyError):
            project_number = ""
        return cls(
            id=row["id"],
            name=row["name"],
            client=row["client"],
            color=row["color"],
            keywords=keywords or "",
            billable=billable,
            archived=bool(row["archived"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            project_number=project_number or "",
        )

    def keyword_list(self) -> list[str]:
        """Return keywords as a list of lowercase strings."""
        if not self.keywords:
            return []
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]

    def resolved_project_number(self) -> str:
        """The FieldFlow job code for this project, best effort.

        Prefers the dedicated column, then the leading token of the display
        name ("P-2842 — Lane Cove"), then a keyword that looks like a code.
        FieldFlow matches on this, so a wrong guess is better caught by the
        review screen than silently dropped here — anything without a digit
        is not offered.
        """
        if self.project_number.strip():
            return self.project_number.strip()

        head = re.split(r"\s+[\u2014\u2013-]\s+", self.name.strip(), maxsplit=1)[0]
        if _looks_like_code(head):
            return head

        for keyword in self.keyword_list():
            if _looks_like_code(keyword):
                return keyword
        return ""


@dataclass
class TimeEntry:
    id: int
    project_id: int
    start_time: datetime
    end_time: datetime
    note: str
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "TimeEntry":
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
