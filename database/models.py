"""Dataclass representations of database rows."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Activity:
    id: int
    timestamp: datetime
    process: str
    title: str
    idle: bool
    duration_s: int

    @classmethod
    def from_row(cls, row) -> "Activity":
        return cls(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            process=row["process"],
            title=row["title"],
            idle=bool(row["idle"]),
            duration_s=row["duration_s"],
        )


@dataclass
class Project:
    id: int
    name: str
    client: str
    color: str
    keywords: str
    archived: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "Project":
        # Handle older DBs without keywords column
        try:
            keywords = row["keywords"]
        except (IndexError, KeyError):
            keywords = ""
        return cls(
            id=row["id"],
            name=row["name"],
            client=row["client"],
            color=row["color"],
            keywords=keywords or "",
            archived=bool(row["archived"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def keyword_list(self) -> list[str]:
        """Return keywords as a list of lowercase strings."""
        if not self.keywords:
            return []
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]


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
