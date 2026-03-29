"""System tray icon with context menu."""

import math

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtCore import Signal, QPointF, QRectF, Qt


def create_app_icon(size: int = 128) -> QIcon:
    """Create a tree + clock icon for the app."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size  # shorthand

    # Background circle
    painter.setBrush(QColor("#1a3a2a"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, s, s)

    # Inner gradient ring
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#2E86AB"), s * 0.03))
    painter.drawEllipse(int(s * 0.04), int(s * 0.04),
                        int(s * 0.92), int(s * 0.92))

    # Tree trunk
    trunk_w = s * 0.06
    trunk_x = s * 0.5 - trunk_w / 2
    trunk_top = s * 0.42
    trunk_bot = s * 0.72
    painter.setBrush(QColor("#8B6914"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(trunk_x, trunk_top, trunk_w, trunk_bot - trunk_top), 2, 2)

    # Tree canopy (three overlapping circles)
    canopy_color = QColor("#2D8C4E")
    painter.setBrush(canopy_color)
    cx, cy = s * 0.5, s * 0.35
    r = s * 0.16
    painter.drawEllipse(QPointF(cx, cy), r, r)
    painter.drawEllipse(QPointF(cx - r * 0.7, cy + r * 0.5), r * 0.85, r * 0.85)
    painter.drawEllipse(QPointF(cx + r * 0.7, cy + r * 0.5), r * 0.85, r * 0.85)
    # Lighter highlight
    painter.setBrush(QColor("#3DAF62"))
    painter.drawEllipse(QPointF(cx, cy - r * 0.15), r * 0.7, r * 0.7)

    # Clock face at bottom-right
    clock_r = s * 0.2
    clock_cx = s * 0.72
    clock_cy = s * 0.72
    painter.setBrush(QColor("#2E86AB"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(clock_cx, clock_cy), clock_r, clock_r)
    painter.setBrush(QColor("#1B5E7B"))
    painter.drawEllipse(QPointF(clock_cx, clock_cy), clock_r * 0.85, clock_r * 0.85)

    # Clock hands
    painter.setPen(QPen(QColor("white"), max(1.5, s * 0.02), Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    # Hour hand (pointing to ~10 o'clock)
    angle_h = math.radians(-60)
    painter.drawLine(QPointF(clock_cx, clock_cy),
                     QPointF(clock_cx + math.cos(angle_h) * clock_r * 0.5,
                             clock_cy + math.sin(angle_h) * clock_r * 0.5))
    # Minute hand (pointing to ~12 o'clock)
    angle_m = math.radians(-90)
    painter.drawLine(QPointF(clock_cx, clock_cy),
                     QPointF(clock_cx + math.cos(angle_m) * clock_r * 0.65,
                             clock_cy + math.sin(angle_m) * clock_r * 0.65))
    # Center dot
    painter.setBrush(QColor("white"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(clock_cx, clock_cy), s * 0.015, s * 0.015)

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """System tray icon for Treetime."""

    show_window_requested = Signal()
    quit_requested = Signal()
    pause_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(create_app_icon(64))
        self.setToolTip("Treetime — Tracking")
        self._paused = False

        # Context menu
        menu = QMenu()
        self._open_action = menu.addAction("Open Timeline")
        self._open_action.triggered.connect(self.show_window_requested.emit)
        menu.addSeparator()
        self._pause_action = menu.addAction("Pause Tracking")
        self._pause_action.triggered.connect(self._toggle_pause)
        menu.addSeparator()
        self._quit_action = menu.addAction("Quit")
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(menu)

        # Double-click opens window
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_action.setText("Resume Tracking" if self._paused else "Pause Tracking")
        self.setToolTip(
            "Treetime — Paused" if self._paused else "Treetime — Tracking"
        )
        self.pause_toggled.emit(self._paused)

    def update_tracking_info(self, process: str, title: str, idle: bool):
        """Update tooltip with current tracking info."""
        if self._paused:
            return
        if idle:
            self.setToolTip("Treetime — Idle")
        else:
            display = process.replace(".exe", "")
            self.setToolTip(f"Treetime — {display}: {title[:50]}")
