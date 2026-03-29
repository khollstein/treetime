"""Data preparation for the timeline view."""

import sqlite3
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Optional

from database import queries
from database.models import Activity, TimeEntry, Project


@dataclass
class ActivitySegment:
    """A visual segment on the activity bar."""
    start: datetime
    end: datetime
    process: str
    title: str
    idle: bool


@dataclass
class ProjectSegment:
    """A visual segment on the project bar."""
    entry_id: int
    start: datetime
    end: datetime
    project: Project
    note: str


class TimelineModel:
    """Loads and caches a day's data for the timeline widget."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._current_day: Optional[date] = None
        self._activity_segments: list[ActivitySegment] = []
        self._project_segments: list[ProjectSegment] = []
        self._projects_cache: dict[int, Project] = {}

    @property
    def current_day(self) -> Optional[date]:
        return self._current_day

    @property
    def activity_segments(self) -> list[ActivitySegment]:
        return self._activity_segments

    @property
    def project_segments(self) -> list[ProjectSegment]:
        return self._project_segments

    def load_day(self, day: date):
        """Load all data for the given day."""
        self._current_day = day
        self._load_activities(day)
        self._load_time_entries(day)

    def reload(self):
        """Reload data for the current day."""
        if self._current_day:
            self.load_day(self._current_day)

    def _load_activities(self, day: date):
        """Convert activity rows into visual segments."""
        activities = queries.get_activities_for_day(self._conn, day)
        self._activity_segments = []
        for act in activities:
            seg = ActivitySegment(
                start=act.timestamp,
                end=act.timestamp + timedelta(seconds=act.duration_s),
                process=act.process,
                title=act.title,
                idle=act.idle,
            )
            self._activity_segments.append(seg)

    def _load_time_entries(self, day: date):
        """Convert time entry rows into visual segments."""
        entries = queries.get_time_entries_for_day(self._conn, day)
        self._project_segments = []
        for entry in entries:
            project = self._get_project(entry.project_id)
            if project:
                seg = ProjectSegment(
                    entry_id=entry.id,
                    start=entry.start_time,
                    end=entry.end_time,
                    project=project,
                    note=entry.note,
                )
                self._project_segments.append(seg)

    def _get_project(self, project_id: int) -> Optional[Project]:
        if project_id not in self._projects_cache:
            self._projects_cache[project_id] = queries.get_project_by_id(
                self._conn, project_id
            )
        return self._projects_cache.get(project_id)

    def invalidate_project_cache(self):
        self._projects_cache.clear()

    def get_activities_in_range(self, start: datetime, end: datetime) -> dict[str, float]:
        """Get process → total seconds within a time range (for selection summary)."""
        result: dict[str, float] = {}
        for seg in self._activity_segments:
            # Calculate overlap
            overlap_start = max(seg.start, start)
            overlap_end = min(seg.end, end)
            if overlap_start < overlap_end:
                seconds = (overlap_end - overlap_start).total_seconds()
                key = seg.process if not seg.idle else "(idle)"
                result[key] = result.get(key, 0) + seconds
        return result
