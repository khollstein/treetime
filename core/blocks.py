"""Turn captured activity into project time blocks, with continuity.

The naive approach — start a block when an activity matches a project, end it
the moment anything else appears — loses most of a real working day.  Opening
Outlook for twenty seconds, glancing at a browser, or thinking with your hands
off the keyboard all cut a two-hour job into a dozen fragments, and the short
ones get thrown away.

So a block survives short interruptions.  If the same project is recognised on
both sides of a brief gap, the gap belongs to that project: the user never
stopped working on it, they just looked at something else.  Only a long gap, a
genuine switch to another job, or the computer going to sleep ends a block.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

# Run kinds
MATCH = "match"      # recognised as a project
GAP = "gap"          # unmatched window, idle, or a hole in the recording
HARD = "hard"        # computer asleep/locked — never bridged


@dataclass
class BlockOptions:
    """Tuning for how forgiving block building is."""

    # Longest stretch of unmatched activity or idle time that can sit inside a
    # block without ending it.
    gap_s: int = 300
    # Longest stretch recognised as a *different* project that can be absorbed
    # into the surrounding block (a quick glance at another job's email).
    # 0 disables this entirely.
    short_switch_s: int = 60
    # Blocks shorter than this are not worth an entry.
    min_block_s: int = 60

    @classmethod
    def from_settings(cls, conn) -> "BlockOptions":
        """Read the options from app_settings, falling back to the defaults."""
        from database.queries import get_setting

        def _int(key: str, default: int) -> int:
            try:
                return max(0, int(get_setting(conn, key, str(default)) or default))
            except (TypeError, ValueError):
                return default

        return cls(
            gap_s=_int("continuity_gap_s", cls.gap_s),
            short_switch_s=_int("continuity_switch_s", cls.short_switch_s),
            min_block_s=_int("min_block_s", cls.min_block_s),
        )


@dataclass
class Block:
    """A contiguous stretch of time attributable to one project."""

    project: object
    start: datetime
    end: datetime
    bridged_s: float = 0.0     # seconds of interruption absorbed
    bridged_count: int = 0     # how many interruptions were absorbed

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass
class _Run:
    start: datetime
    end: datetime
    kind: str
    project: object = None
    bridged_s: float = 0.0
    bridged_count: int = 0

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass
class BuildResult:
    blocks: list = field(default_factory=list)
    bridged_s: float = 0.0
    bridged_count: int = 0

    @property
    def total_s(self) -> float:
        return sum(b.duration_s for b in self.blocks)


def _segments_to_runs(segments, matcher) -> list[_Run]:
    """Label each activity segment and merge neighbours that agree."""
    runs: list[_Run] = []

    def _append(start, end, kind, project=None):
        if runs:
            last = runs[-1]
            if last.kind == kind and last.project is project and start <= last.end:
                last.end = max(last.end, end)
                return
            # Overlapping activity rows shouldn't happen, but a run that
            # started before the previous one ended would break the ordering
            # everything downstream relies on.
            start = max(start, last.end)
        if end <= start:
            return
        runs.append(_Run(start=start, end=end, kind=kind, project=project))

    for seg in sorted(segments, key=lambda s: s.start):
        # A hole in the recording (app restarted, poll missed) is time we know
        # nothing about — treat it like any other gap so it counts against the
        # bridging budget instead of silently vanishing.
        if runs and seg.start > runs[-1].end:
            _append(runs[-1].end, seg.start, GAP)

        if getattr(seg, "offline", False):
            _append(seg.start, seg.end, HARD)
            continue
        if getattr(seg, "idle", False):
            _append(seg.start, seg.end, GAP)
            continue

        project = matcher.match(seg.process, seg.title) if matcher else None
        if project is None:
            _append(seg.start, seg.end, GAP)
        else:
            _append(seg.start, seg.end, MATCH, project)

    return runs


def _absorb_interruptions(runs: list[_Run], options: BlockOptions) -> list[_Run]:
    """Merge short interruptions into the project blocks that surround them."""
    runs = list(runs)
    # Each pass can create new neighbours worth merging, so repeat until the
    # list stops changing. Bounded so a pathological day can't spin.
    for _ in range(len(runs) + 1):
        merged_index = None
        for i in range(1, len(runs) - 1):
            middle, before, after = runs[i], runs[i - 1], runs[i + 1]
            if middle.kind == HARD:
                continue
            if before.kind != MATCH or after.kind != MATCH:
                continue
            if before.project is not after.project:
                continue

            if middle.kind == GAP:
                limit = options.gap_s
            else:
                # A different project. Only absorb a genuinely fleeting visit,
                # and never one longer than the work on either side of it.
                limit = options.short_switch_s
                if limit <= 0:
                    continue
                if (middle.duration_s > before.duration_s
                        or middle.duration_s > after.duration_s):
                    continue

            if middle.duration_s > limit:
                continue

            merged_index = i
            break

        if merged_index is None:
            break

        middle = runs[merged_index]
        before = runs[merged_index - 1]
        after = runs[merged_index + 1]
        before.end = after.end
        before.bridged_s += middle.duration_s + middle.bridged_s + after.bridged_s
        before.bridged_count += 1 + middle.bridged_count + after.bridged_count
        del runs[merged_index:merged_index + 2]

    return runs


def _subtract_covered(block: Block, covered) -> list[Block]:
    """Split *block* around time that already has an entry."""
    pieces = [block]
    for cov_start, cov_end in covered:
        if cov_end <= cov_start:
            continue
        next_pieces: list[Block] = []
        for piece in pieces:
            if cov_end <= piece.start or cov_start >= piece.end:
                next_pieces.append(piece)
                continue
            if cov_start > piece.start:
                next_pieces.append(Block(piece.project, piece.start, cov_start))
            if cov_end < piece.end:
                next_pieces.append(Block(piece.project, cov_end, piece.end))
        pieces = next_pieces
        if not pieces:
            break

    if len(pieces) == 1 and pieces[0] is block:
        return pieces

    # Bridged time belongs to whichever piece survived; attribute it to the
    # longest one so the reported totals stay honest.
    if pieces and block.bridged_s:
        longest = max(pieces, key=lambda p: p.duration_s)
        longest.bridged_s = block.bridged_s
        longest.bridged_count = block.bridged_count
    return pieces


def build_blocks(segments: Iterable, matcher,
                 options: Optional[BlockOptions] = None,
                 covered: Optional[Iterable] = None) -> BuildResult:
    """Group *segments* into project blocks.

    ``segments`` need ``start``, ``end``, ``process``, ``title``, ``idle`` and
    ``offline``.  ``covered`` is an iterable of ``(start, end)`` ranges that
    already have time entries; blocks are split around them so nothing is
    double-booked.
    """
    options = options or BlockOptions()
    segments = [s for s in segments if s.end > s.start]
    if not segments or matcher is None or matcher.is_empty:
        return BuildResult()

    runs = _absorb_interruptions(_segments_to_runs(segments, matcher), options)

    blocks: list[Block] = []
    for run in runs:
        if run.kind != MATCH:
            continue
        blocks.append(Block(
            project=run.project,
            start=run.start,
            end=run.end,
            bridged_s=run.bridged_s,
            bridged_count=run.bridged_count,
        ))

    covered = list(covered or [])
    if covered:
        split: list[Block] = []
        for block in blocks:
            split.extend(_subtract_covered(block, covered))
        blocks = split

    blocks = [b for b in blocks if b.duration_s >= options.min_block_s]
    blocks.sort(key=lambda b: b.start)

    return BuildResult(
        blocks=blocks,
        bridged_s=sum(b.bridged_s for b in blocks),
        bridged_count=sum(b.bridged_count for b in blocks),
    )
