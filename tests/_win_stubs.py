"""Stand-ins for the Windows-only modules, so UI code can be imported anywhere.

Only used when the real modules are missing (i.e. not on Windows). Importing
this has no effect on a developer machine running the real thing.
"""

import ctypes
import sys
import types


def install():
    """Register stubs for any Windows module that isn't available."""
    try:
        import win32gui  # noqa: F401
        return False
    except ImportError:
        pass

    win32gui = types.ModuleType("win32gui")
    win32gui.GetForegroundWindow = lambda: 0
    win32gui.GetWindowText = lambda hwnd: ""
    sys.modules["win32gui"] = win32gui

    win32process = types.ModuleType("win32process")
    win32process.GetWindowThreadProcessId = lambda hwnd: (0, 0)
    sys.modules["win32process"] = win32process

    try:
        import psutil  # noqa: F401
    except ImportError:
        psutil = types.ModuleType("psutil")

        class _NoSuchProcess(Exception):
            pass

        class _AccessDenied(Exception):
            pass

        psutil.NoSuchProcess = _NoSuchProcess
        psutil.AccessDenied = _AccessDenied
        psutil.Process = lambda pid: types.SimpleNamespace(name=lambda: "python")
        sys.modules["psutil"] = psutil

    # ctypes.wintypes refuses to import off Windows.
    wintypes = types.ModuleType("ctypes.wintypes")
    wintypes.UINT = ctypes.c_uint
    wintypes.DWORD = ctypes.c_ulong
    sys.modules["ctypes.wintypes"] = wintypes
    ctypes.wintypes = wintypes

    if not hasattr(ctypes, "windll"):
        ctypes.windll = types.SimpleNamespace(
            user32=types.SimpleNamespace(GetLastInputInfo=lambda ref: 0),
            kernel32=types.SimpleNamespace(GetTickCount=lambda: 0),
            shell32=types.SimpleNamespace(
                SetCurrentProcessExplicitAppUserModelID=lambda _id: 0),
        )
    return True
