"""Detect Windows session lock/unlock via WTS notifications."""

import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal

WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

wtsapi32 = ctypes.windll.wtsapi32


class SessionMonitor(QWidget):
    """Hidden widget that listens for Windows session lock/unlock events.

    Covers screen lock, sleep, and hibernate — Windows sends
    WTS_SESSION_LOCK / WTS_SESSION_UNLOCK for all of these.
    """

    session_locked = Signal()
    session_unlocked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TreetimeSessionMonitor")
        self.resize(0, 0)
        self.hide()
        self._registered = False

    def register(self):
        """Register for session change notifications.
        Must be called after the widget has a valid winId.
        """
        hwnd = int(self.winId())
        result = wtsapi32.WTSRegisterSessionNotification(
            ctypes.wintypes.HWND(hwnd), NOTIFY_FOR_THIS_SESSION
        )
        self._registered = bool(result)

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_WTSSESSION_CHANGE:
                    if msg.wParam == WTS_SESSION_LOCK:
                        self.session_locked.emit()
                    elif msg.wParam == WTS_SESSION_UNLOCK:
                        self.session_unlocked.emit()
            except Exception:
                pass  # Don't crash the app on message parsing errors
        return super().nativeEvent(event_type, message)

    def cleanup(self):
        """Unregister from session change notifications."""
        if self._registered:
            try:
                hwnd = int(self.winId())
                wtsapi32.WTSUnRegisterSessionNotification(
                    ctypes.wintypes.HWND(hwnd)
                )
            except Exception:
                pass
            self._registered = False
