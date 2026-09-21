"""Shared test doubles."""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DAY = datetime(2026, 9, 21, 8, 0, 0)


@dataclass
class FakeProject:
    id: int
    name: str
    keywords: str = ""
    project_number: str = ""
    billable: bool = True
    client: str = ""
    color: str = "#4C6EF5"

    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]


@dataclass
class FakeSegment:
    start: datetime
    end: datetime
    process: str = "chrome.exe"
    title: str = ""
    idle: bool = False
    offline: bool = False


def seg(offset_min, length_min, title="", process="chrome.exe",
        idle=False, offline=False):
    """A segment starting *offset_min* after 08:00 and lasting *length_min*."""
    start = DAY + timedelta(minutes=offset_min)
    return FakeSegment(
        start=start,
        end=start + timedelta(minutes=length_min),
        process=process,
        title=title,
        idle=idle,
        offline=offline,
    )


def at(offset_min):
    return DAY + timedelta(minutes=offset_min)
