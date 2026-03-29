"""Entry point for Treetime — single-instance guard + launch."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _acquire_single_instance_lock():
    """Ensure only one instance runs at a time (Windows)."""
    import win32event
    import win32api
    import winerror

    mutex_name = "Treetime_SingleInstance_Mutex"
    mutex = win32event.CreateMutex(None, False, mutex_name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        print("Treetime is already running.")
        sys.exit(0)
    return mutex  # Must keep reference to prevent GC


def main():
    mutex = _acquire_single_instance_lock()

    from app import TreetimeApp
    app = TreetimeApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
