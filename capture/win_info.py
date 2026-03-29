"""Get active window information using win32gui."""

import win32gui
import win32process
import psutil


def get_active_window_info() -> tuple[str, str]:
    """Return (process_name, window_title) for the currently active window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ("unknown", "")
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process = "unknown"
        return (process, title)
    except Exception:
        return ("unknown", "")
