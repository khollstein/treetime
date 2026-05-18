"""Application configuration and paths."""

import os

APP_NAME = "Treetime"
APP_VERSION = "0.3.5"

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), APP_NAME)
DB_PATH = os.path.join(DATA_DIR, "data.db")

# Capture defaults
DEFAULT_POLL_INTERVAL_MS = 5000
DEFAULT_IDLE_THRESHOLD_S = 300
