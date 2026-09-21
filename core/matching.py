"""Project matching — shared by the timeline, auto-assign and reports.

Matching is deliberately forgiving about how a project number is written.
FieldFlow stores ``P-2842``, but the same job turns up in window titles as
``P2842``, ``P 2842`` or ``C:\\Jobs\\P-2842 Lane Cove\\report.docx``.  A plain
substring test misses most of those, which is the main reason activity goes
unmatched and time blocks get dropped.

Rules:

* A keyword containing a digit (project numbers, "tree 71") is matched with
  flexible separators and hard boundaries — ``P-2842`` hits ``p2842`` and
  ``p_2842`` but never ``P-28421``.
* A purely alphabetic keyword ("council", "QGIS") keeps plain substring
  behaviour, so plurals and compounds still match.
"""

import re
from typing import Iterable, Optional

_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_HAS_DIGIT_RE = re.compile(r"\d")

# A keyword that squashes down to fewer characters than this is too weak to
# match on its own (e.g. "P1" would hit half the file system).
MIN_KEYWORD_LEN = 2

# Project numbers are stronger evidence than a generic word of the same length.
_DIGIT_BONUS = 3


def squash(text: str) -> str:
    """Lowercase *text* and strip everything that is not a letter or digit."""
    return _SPLIT_RE.sub("", (text or "").lower())


def build_keyword_pattern(keyword: str) -> Optional[re.Pattern]:
    """Compile a forgiving pattern for *keyword*, or None if it is too weak.

    ``"P-2842"`` becomes a pattern that matches ``p-2842``, ``p2842`` and
    ``p 2842`` but not ``p28421``.
    """
    parts = [p for p in _SPLIT_RE.split((keyword or "").lower()) if p]
    if not parts:
        return None
    if sum(len(p) for p in parts) < MIN_KEYWORD_LEN:
        return None

    if _HAS_DIGIT_RE.search(keyword):
        # Separators in the keyword may be written any way (or not at all),
        # but the match must not run into a neighbouring alphanumeric.
        body = r"[^a-z0-9]*".join(re.escape(p) for p in parts)
        return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")

    # Alphabetic keyword — plain substring, separators as written.
    return re.compile(re.escape(" ".join(parts)).replace(r"\ ", r"[^a-z0-9]+"))


def keyword_score(keyword: str) -> int:
    """How specific *keyword* is. Longer wins; project numbers get a bonus."""
    base = len(squash(keyword))
    return base + (_DIGIT_BONUS if _HAS_DIGIT_RE.search(keyword or "") else 0)


class ProjectMatcher:
    """Matches activity text against a fixed set of projects.

    Build one per refresh and reuse it — compiling the patterns once keeps
    this cheap enough to call from a paint event.
    """

    def __init__(self, projects: Iterable):
        self._entries = []  # (pattern, score, project)
        for project in projects:
            for keyword in self._keywords_for(project):
                pattern = build_keyword_pattern(keyword)
                if pattern is not None:
                    self._entries.append((pattern, keyword_score(keyword), project))
        # Most specific first, so the first hit is the best hit.
        self._entries.sort(key=lambda e: -e[1])
        self._cache: dict[str, Optional[object]] = {}

    @staticmethod
    def _keywords_for(project) -> list[str]:
        keywords = list(project.keyword_list())
        number = (getattr(project, "project_number", "") or "").strip()
        if number:
            keywords.append(number)
        return keywords

    @property
    def is_empty(self) -> bool:
        return not self._entries

    def match_text(self, text: str):
        """Return the best-matching project for *text*, or None."""
        if not text or not self._entries:
            return None
        lowered = text.lower()
        cached = self._cache.get(lowered, False)
        if cached is not False:
            return cached
        result = None
        for pattern, _score, project in self._entries:
            if pattern.search(lowered):
                result = project
                break
        self._cache[lowered] = result
        return result

    def match(self, process: str, title: str):
        """Return the best-matching project for a captured window."""
        return self.match_text(f"{process or ''} {title or ''}")
