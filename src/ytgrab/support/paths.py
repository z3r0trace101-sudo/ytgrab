"""Application file-system locations for Windows and other desktop systems."""

import os
from pathlib import Path


def downloads_folder() -> Path:
    """Return the current user's conventional Downloads folder."""
    candidate = Path.home() / "Downloads"
    return candidate if candidate.exists() else Path.home()


def app_data_folder() -> Path:
    """Return ytgrab's per-user application-data directory."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base = Path(root) if root else Path.home() / ".local" / "share"
    folder = base / "ytgrab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def log_folder() -> Path:
    """Return and create the application log directory."""
    folder = app_data_folder() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
