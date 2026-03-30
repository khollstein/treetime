"""Treetime-style three-column timeline with auto-assign rules."""

import sqlite3
from datetime import date, datetime, timedelta
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDateEdit, QLabel,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt, QRectF, Signal, QDate
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from ui.styles import color_for_process, IDLE_COLOR, OFFLINE_COLOR, get_theme
from ui.timeline.timeline_model import TimelineModel


SLOT_HEIGHT = 48


def _get_time_slots(model, zoom_minutes):
    day = model.current_day or date.today()
    segments = model.activity_segments

    if not segments:
        now = datetime.now()
        if day == date.today():
            start_hour = max(0, now.hour - 1)
            end_hour = min(24, now.hour + 2)
        else:
            return []
    else:
        start_hour = max(0, segments[0].start.hour)
        end_hour = min(24, segments[-1].end.hour + 1)
        if day == date.today():
            end_hour = max(end_hour, min(24, datetime.now().hour + 1))

    slots = []
    current = datetime(day.year, day.month, day.day, start_hour)
    end_dt = datetime(day.year, day.month, day.day, min(23, end_hour), 59, 59)
    if end_hour >= 24:
        end_dt = datetime(day.year, day.month, day.day, 23, 59, 59)

    while current <= end_dt:
        slots.append(current)
        current += timedelta(minutes=zoom_minutes)
    return slots


class _KeywordMatchCache:
    """Cache keyword matches to avoid DB queries in paintEvent."""

    def __init__(self):
        self._cache = {}
        self._projects = None

    def invalidate(self):
        self._cache.clear()
        self._projects = None

    def find_match(self, conn, process, title):
        key = (process, title)
        if key in self._cache:
            return self._cache[key]
        if self._projects is None:
            from database.queries import get_all_projects
            self._projects = get_all_projects(conn)
        search_text = f"{process} {title}".lower()
        best, best_score = None, 0
        for p in self._projects:
            for kw in p.keyword_list():
                if kw in search_text and len(kw) > best_score:
                    best_score = len(kw)
                    best = p
        self._cache[key] = best
        return best

_match_cache = _KeywordMatchCache()


# ── Memory Aid Column ──────────────────────────────────────────────

class MemoryAidColumn(QWidget):
    """Left column: captured activities. Click to assign. Shows rule matches."""

    assign_requested = Signal(datetime, datetime, dict)

    def __init__(self, model, conn, parent=None):
        super().__init__(parent)
        self._model = model
        self._conn = conn
        self._zoom_minutes = 15
        self._selecting = False
        self._sel_start_y = 0
        self._sel_end_y = 0
        self._hover_slot = -1
        self.setMinimumWidth(320)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def set_zoom(self, minutes):
        self._zoom_minutes = minutes
        self.updateGeometry()
        self.update()

    def _slots(self):
        return _get_time_slots(self._model, self._zoom_minutes)

    def _y_to_time(self, y):
        slots = self._slots()
        if not slots:
            return datetime.now()
        idx = max(0, min(len(slots) - 1, int(y / SLOT_HEIGHT)))
        frac = max(0, min(1, (y - idx * SLOT_HEIGHT) / SLOT_HEIGHT))
        return slots[idx] + timedelta(minutes=frac * self._zoom_minutes)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(320, max(400, len(self._slots()) * SLOT_HEIGHT + 20))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = get_theme()

        painter.fillRect(self.rect(), QColor(t.bg_primary))

        slots = self._slots()
        if not slots:
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No activity recorded")
            painter.end()
            return

        segments = self._model.activity_segments
        y = 0

        for i, slot_start in enumerate(slots):
            slot_end = slot_start + timedelta(minutes=self._zoom_minutes)

            # Row background
            if i == self._hover_slot:
                bg = QColor(t.slot_hover)
            elif i % 2 == 0:
                bg = QColor(t.slot_even)
            else:
                bg = QColor(t.slot_odd)
            painter.fillRect(QRectF(0, y, self.width(), SLOT_HEIGHT), bg)

            # Grid line
            painter.setPen(QPen(QColor(t.border_subtle), 1))
            painter.drawLine(0, y, self.width(), y)

            # Time label
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(8, y, 44, SLOT_HEIGHT),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                             slot_start.strftime("%H:%M"))

            # Find activities in this slot
            slot_activities = []
            for seg in segments:
                overlap_start = max(seg.start, slot_start)
                overlap_end = min(seg.end, slot_end)
                if overlap_start < overlap_end:
                    dur = (overlap_end - overlap_start).total_seconds()
                    slot_activities.append((seg, dur))

            if slot_activities:
                by_proc = defaultdict(lambda: {"duration": 0, "title": "", "idle": False,
                                               "offline": False, "process": "", "max_dur": 0})
                for seg, dur in slot_activities:
                    key = "(offline)" if seg.offline else ("(idle)" if seg.idle else seg.process)
                    by_proc[key]["duration"] += dur
                    by_proc[key]["process"] = seg.process
                    by_proc[key]["idle"] = seg.idle
                    by_proc[key]["offline"] = seg.offline
                    if dur > by_proc[key]["max_dur"]:
                        by_proc[key]["title"] = seg.title
                        by_proc[key]["max_dur"] = dur

                sorted_procs = sorted(by_proc.items(), key=lambda x: -x[1]["duration"])
                entry_x = 56
                entry_y = y + 5
                item_h = min(SLOT_HEIGHT - 10, 22 if len(sorted_procs) > 1 else SLOT_HEIGHT - 10)

                for proc_name, info in sorted_procs[:2]:
                    dur_min = max(1, int(info["duration"] / 60))
                    title = info["title"]

                    # Color indicator
                    if info["offline"]:
                        bar_color = QColor(OFFLINE_COLOR)
                    elif info["idle"]:
                        bar_color = QColor(IDLE_COLOR)
                    else:
                        bar_color = QColor(color_for_process(info["process"]))
                    painter.setBrush(bar_color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(QRectF(entry_x, entry_y + 2, 4, item_h - 4), 2, 2)

                    # Check for keyword rule match — show dot
                    if not info["idle"] and not info["offline"]:
                        match = _match_cache.find_match(self._conn, info["process"], title)
                        if match:
                            painter.setBrush(QColor(match.color))
                            painter.drawEllipse(QRectF(entry_x + 7, entry_y + item_h/2 - 3, 6, 6))

                    # Title
                    painter.setPen(QColor(t.text_primary))
                    painter.setFont(QFont("Segoe UI", 9))
                    text_x = entry_x + 16
                    max_w = self.width() - text_x - 58
                    fm = painter.fontMetrics()
                    elided = fm.elidedText(title if title else proc_name,
                                           Qt.TextElideMode.ElideRight, max_w)
                    painter.drawText(QRectF(text_x, entry_y, max_w, item_h),
                                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                     elided)

                    # Duration
                    painter.setPen(QColor(t.text_muted))
                    painter.setFont(QFont("Segoe UI", 8))
                    painter.drawText(
                        QRectF(self.width() - 54, entry_y, 48, item_h),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        f"{dur_min} min",
                    )
                    entry_y += item_h + 2

            y += SLOT_HEIGHT

        # Selection overlay
        if self._selecting or self._sel_start_y != self._sel_end_y:
            y1 = min(self._sel_start_y, self._sel_end_y)
            y2 = max(self._sel_start_y, self._sel_end_y)
            painter.fillRect(QRectF(0, y1, self.width(), y2 - y1), QColor(t.selection_bg))
            painter.setPen(QPen(QColor(t.accent), 2))
            painter.drawRect(QRectF(1, y1, self.width() - 2, y2 - y1))

        # Now line
        day = self._model.current_day or date.today()
        if day == date.today() and slots:
            first = slots[0]
            now_secs = (datetime.now() - first).total_seconds()
            slot_secs = self._zoom_minutes * 60
            now_y = (now_secs / slot_secs) * SLOT_HEIGHT
            if 0 <= now_y <= len(slots) * SLOT_HEIGHT:
                painter.setPen(QPen(QColor(t.now_line), 2))
                painter.drawLine(0, int(now_y), self.width(), int(now_y))

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._sel_start_y = event.position().y()
            self._sel_end_y = event.position().y()
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._sel_end_y = event.position().y()
            self.update()
        else:
            slot = int(event.position().y() / SLOT_HEIGHT)
            if slot != self._hover_slot:
                self._hover_slot = slot
                self.update()

    def mouseReleaseEvent(self, event):
        if self._selecting and event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
            y1 = min(self._sel_start_y, self._sel_end_y)
            y2 = max(self._sel_start_y, self._sel_end_y)
            if y2 - y1 < 8:
                slot_idx = int(event.position().y() / SLOT_HEIGHT)
                y1 = slot_idx * SLOT_HEIGHT
                y2 = y1 + SLOT_HEIGHT
            start_time = self._y_to_time(y1)
            end_time = self._y_to_time(y2)
            if (end_time - start_time).total_seconds() >= 30:
                activities = self._model.get_activities_in_range(start_time, end_time)
                self.assign_requested.emit(start_time, end_time, activities)
            self._sel_start_y = 0
            self._sel_end_y = 0
            self.update()

    def leaveEvent(self, event):
        self._hover_slot = -1
        self.update()


# ── Time Entries Column ─────────────────────────────────────────────

class TimeEntriesColumn(QWidget):
    entry_clicked = Signal(int)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._zoom_minutes = 15
        self.setMinimumWidth(220)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_zoom(self, minutes):
        self._zoom_minutes = minutes
        self.updateGeometry()
        self.update()

    def _slots(self):
        return _get_time_slots(self._model, self._zoom_minutes)

    def _time_to_y(self, dt):
        slots = self._slots()
        if not slots:
            return 0
        first = slots[0]
        secs = (dt - first).total_seconds()
        slot_secs = self._zoom_minutes * 60
        return (secs / slot_secs) * SLOT_HEIGHT

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(220, max(400, len(self._slots()) * SLOT_HEIGHT + 20))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = get_theme()

        painter.fillRect(self.rect(), QColor(t.bg_primary))

        slots = self._slots()
        if not slots:
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Assign from\nMemory Aid")
            painter.end()
            return

        # Grid
        for i, slot_start in enumerate(slots):
            y = i * SLOT_HEIGHT
            bg = QColor(t.slot_even if i % 2 == 0 else t.slot_odd)
            painter.fillRect(QRectF(0, y, self.width(), SLOT_HEIGHT), bg)
            painter.setPen(QPen(QColor(t.border_subtle), 1))
            painter.drawLine(0, y, self.width(), y)
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(QRectF(4, y, 36, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                             slot_start.strftime("%H:%M"))

        # Project blocks
        for seg in self._model.project_segments:
            y1 = self._time_to_y(seg.start)
            y2 = self._time_to_y(seg.end)
            h = max(SLOT_HEIGHT * 0.6, y2 - y1)

            color = QColor(seg.project.color)
            x, w = 6, self.width() - 12

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y1 + 2, w, h - 4), 8, 8)

            painter.setPen(QColor("white"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(x + 12, y1 + 2, w - 75, h - 4),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             seg.project.name)

            dur = seg.end - seg.start
            mins = int(dur.total_seconds() / 60)
            dur_text = f"{mins // 60}h {mins % 60}m" if mins >= 60 else f"{mins} min"
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRectF(x + w - 62, y1 + 2, 55, h - 4),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             dur_text)

        # Now line
        day = self._model.current_day or date.today()
        if day == date.today() and slots:
            now_y = self._time_to_y(datetime.now())
            if 0 <= now_y <= len(slots) * SLOT_HEIGHT:
                painter.setPen(QPen(QColor(t.now_line), 2))
                painter.drawLine(0, int(now_y), self.width(), int(now_y))

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            slots = self._slots()
            if not slots:
                return
            first = slots[0]
            click_secs = (event.position().y() / SLOT_HEIGHT) * self._zoom_minutes * 60
            click_time = first + timedelta(seconds=click_secs)
            for seg in self._model.project_segments:
                if seg.start <= click_time <= seg.end:
                    self.entry_clicked.emit(seg.entry_id)
                    return


# ── Projects Sidebar ────────────────────────────────────────────────

class ProjectsSidebar(QWidget):
    def __init__(self, model, conn, parent=None):
        super().__init__(parent)
        self._model = model
        self._conn = conn
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = get_theme()
        painter.fillRect(self.rect(), QColor(t.bg_primary))

        project_times = defaultdict(float)
        for seg in self._model.project_segments:
            dur = (seg.end - seg.start).total_seconds() / 60.0
            project_times[seg.project.id] += dur

        seen = set()
        projects = []
        for seg in self._model.project_segments:
            if seg.project.id not in seen:
                seen.add(seg.project.id)
                projects.append(seg.project)
        from database.queries import get_all_projects
        for p in get_all_projects(self._conn):
            if p.id not in seen:
                projects.append(p)

        if not projects:
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No projects yet\n\nGo to Projects tab\nto add some")
            painter.end()
            return

        # Split into billable and non-billable
        billable = [p for p in projects if p.billable]
        non_billable = [p for p in projects if not p.billable]

        y = 8

        def _draw_project_row(p, y_pos):
            mins = project_times.get(p.id, 0)
            h_text = ""
            if mins >= 60:
                h_text = f"{int(mins // 60)}h {int(mins % 60)}m"
            elif mins > 0:
                h_text = f"{int(mins)} min"

            painter.setBrush(QColor(p.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(8, y_pos, self.width() - 16, 32), 8, 8)

            painter.setPen(QColor("white"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            name = fm.elidedText(p.name, Qt.TextElideMode.ElideRight, self.width() - 88)
            painter.drawText(QRectF(16, y_pos, self.width() - 88, 32),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             name)
            if h_text:
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QRectF(self.width() - 72, y_pos, 58, 32),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 h_text)
            return y_pos + 40

        def _draw_section_header(label, y_pos):
            painter.setPen(QColor(t.text_muted))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(10, y_pos, self.width() - 20, 20),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             label)
            return y_pos + 24

        # Billable section
        if billable:
            if non_billable:  # Only show header if both sections exist
                y = _draw_section_header("Billable", y)
            for p in billable:
                y = _draw_project_row(p, y)

        # Non-billable section
        if non_billable:
            if billable:
                y += 8
            y = _draw_section_header("Non-billable", y)
            for p in non_billable:
                y = _draw_project_row(p, y)

        painter.end()


# ── Main Timeline Widget ───────────────────────────────────────────

class TimelineWidget(QWidget):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._model = TimelineModel(conn)
        self._zoom_minutes = 15

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)

        self._prev_btn = QPushButton("\u25C0")  # ◀
        self._prev_btn.setFixedSize(32, 32)
        self._prev_btn.clicked.connect(self._go_prev)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("dddd, MMMM d, yyyy")
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.dateChanged.connect(self._on_date_changed)

        self._next_btn = QPushButton("\u25B6")  # ▶
        self._next_btn.setFixedSize(32, 32)
        self._next_btn.clicked.connect(self._go_next)

        self._today_btn = QPushButton("Today")
        self._today_btn.clicked.connect(self._go_today)

        # Auto-assign button
        self._auto_btn = QPushButton("Auto-assign rules")
        self._auto_btn.setObjectName("primary")
        self._auto_btn.setToolTip("Apply keyword rules to assign unmatched activities")
        self._auto_btn.clicked.connect(self._auto_assign)

        zoom_label = QLabel("Zoom:")
        self._zoom_combo = QComboBox()
        self._zoom_combo.addItems(["5 min", "10 min", "15 min", "30 min", "60 min"])
        self._zoom_combo.setCurrentIndex(2)
        self._zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)

        tb_layout.addWidget(self._prev_btn)
        tb_layout.addWidget(self._date_edit)
        tb_layout.addWidget(self._next_btn)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(self._today_btn)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(self._auto_btn)
        tb_layout.addStretch()
        tb_layout.addWidget(zoom_label)
        tb_layout.addWidget(self._zoom_combo)
        layout.addWidget(toolbar)

        # Headers
        headers = QWidget()
        hdr_layout = QHBoxLayout(headers)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(0)

        hdr_layout.addWidget(self._make_header("Memory Aid",
                             "Click activities to assign \u2022 dots show rule matches"), 2)
        hdr_layout.addWidget(self._vsep())
        hdr_layout.addWidget(self._make_header("Time Entries", "Assigned project blocks"), 3)
        hdr_layout.addWidget(self._vsep())
        hdr_layout.addWidget(self._make_header("Projects", "Today's totals"), 1)
        layout.addWidget(headers)

        # Scrollable content with resizable columns
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(3)

        self._memory_aid = MemoryAidColumn(self._model, conn)
        self._memory_aid.assign_requested.connect(self._on_assign_from_memory)

        self._time_entries = TimeEntriesColumn(self._model)
        self._time_entries.entry_clicked.connect(self._on_entry_clicked)

        self._projects_sidebar = ProjectsSidebar(self._model, conn)
        self._projects_sidebar.setMaximumWidth(16777215)  # remove max width constraint
        self._projects_sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._splitter.addWidget(self._memory_aid)
        self._splitter.addWidget(self._time_entries)
        self._splitter.addWidget(self._projects_sidebar)
        self._splitter.setSizes([320, 300, 180])
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 3)
        self._splitter.setStretchFactor(2, 1)

        scroll.setWidget(self._splitter)
        layout.addWidget(scroll, 1)

        self._load_date(date.today())

    def _make_header(self, title, subtitle):
        t = get_theme()
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 8, 12, 6)
        lay.setSpacing(1)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {t.text_primary};")
        sub = QLabel(subtitle)
        sub.setStyleSheet(f"font-size: 10px; color: {t.text_muted};")
        lay.addWidget(lbl)
        lay.addWidget(sub)
        return w

    def _vsep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        return sep

    def _load_date(self, day):
        self._model.load_day(day)
        self._refresh()

    def _refresh(self):
        self._memory_aid.updateGeometry()
        self._memory_aid.update()
        self._time_entries.updateGeometry()
        self._time_entries.update()
        self._projects_sidebar.update()

    def reload(self):
        self._model.reload()
        self._refresh()

    def _on_date_changed(self, qdate):
        self._load_date(date(qdate.year(), qdate.month(), qdate.day()))

    def _go_prev(self):
        self._date_edit.setDate(self._date_edit.date().addDays(-1))

    def _go_next(self):
        self._date_edit.setDate(self._date_edit.date().addDays(1))

    def _go_today(self):
        self._date_edit.setDate(QDate.currentDate())

    def _on_zoom_changed(self, index):
        zoom = {0: 5, 1: 10, 2: 15, 3: 30, 4: 60}.get(index, 15)
        self._zoom_minutes = zoom
        self._memory_aid.set_zoom(zoom)
        self._time_entries.set_zoom(zoom)

    def _auto_assign(self):
        """Apply keyword rules: find all unassigned activity segments, match
        against project keywords, and create time entries automatically."""
        from database.queries import (
            get_all_projects, insert_time_entry, get_time_entries_for_day,
        )

        day = self._model.current_day or date.today()
        segments = self._model.activity_segments
        existing_entries = get_time_entries_for_day(self._conn, day)
        projects = get_all_projects(self._conn)

        if not segments or not projects:
            QMessageBox.information(self, "Auto-assign",
                                    "No activities or no projects with keywords to match.")
            return

        # Build keyword → project mapping
        keyword_map = []
        for p in projects:
            for kw in p.keyword_list():
                keyword_map.append((kw, p))

        if not keyword_map:
            QMessageBox.information(self, "Auto-assign",
                "No projects have keywords set.\n\n"
                "Go to Projects tab, edit a project, and add keywords like:\n"
                "  QGIS, council, tree 71\n\n"
                "These will be matched against your window titles.")
            return

        # Find unassigned segments and match them
        assigned_count = 0
        # Group consecutive segments with the same match into blocks
        current_match = None
        block_start = None
        block_end = None

        def _is_covered(seg_start, seg_end):
            """Check if a segment is already covered by an existing time entry."""
            mid = seg_start + (seg_end - seg_start) / 2
            for entry in existing_entries:
                if entry.start_time <= mid <= entry.end_time:
                    return True
            return False

        def _flush_block():
            nonlocal assigned_count, block_start, block_end, current_match
            if current_match and block_start and block_end:
                insert_time_entry(self._conn, current_match.id, block_start, block_end)
                assigned_count += 1
            current_match = None
            block_start = None
            block_end = None

        for seg in segments:
            if seg.idle or seg.offline:
                _flush_block()
                continue

            seg_end = seg.timestamp + timedelta(seconds=seg.duration_s)
            if _is_covered(seg.timestamp, seg_end):
                _flush_block()
                continue

            # Check keyword match
            search = f"{seg.process} {seg.title}".lower()
            match = None
            best_score = 0
            for kw, proj in keyword_map:
                if kw in search:
                    score = len(kw)
                    if score > best_score:
                        best_score = score
                        match = proj

            if match:
                if match == current_match and block_end:
                    # Extend current block
                    block_end = seg_end
                else:
                    _flush_block()
                    current_match = match
                    block_start = seg.timestamp
                    block_end = seg_end
            else:
                _flush_block()

        _flush_block()

        # Reload
        self._model.reload()
        self._model.invalidate_project_cache()
        _match_cache.invalidate()
        self._refresh()

        if assigned_count > 0:
            QMessageBox.information(self, "Auto-assign",
                                    f"Created {assigned_count} time entries from keyword rules.")
        else:
            QMessageBox.information(self, "Auto-assign",
                                    "No new matches found. All matching activities are already assigned.")

    def _on_assign_from_memory(self, start, end, activities):
        from ui.timeline.assignment_dialog import AssignmentDialog
        dlg = AssignmentDialog(self._conn, start, end, activities, parent=self)
        if dlg.exec():
            project_id, note = dlg.result_data()
            from database.queries import insert_time_entry
            insert_time_entry(self._conn, project_id, start, end, note)
            self._model.reload()
            self._model.invalidate_project_cache()
            _match_cache.invalidate()
            self._refresh()

    def _on_entry_clicked(self, entry_id):
        from database.queries import delete_time_entry
        reply = QMessageBox.question(
            self, "Time Entry",
            "Delete this time entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_time_entry(self._conn, entry_id)
            self._model.reload()
            self._refresh()
