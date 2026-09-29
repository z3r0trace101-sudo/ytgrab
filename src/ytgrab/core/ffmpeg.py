"""FFmpeg discovery used by the download service.

FFmpeg does not have to be installed system-wide. If the process that starts
ytgrab (for example the PowerShell launcher, scripts/run.ps1) has already
downloaded a portable FFmpeg build for this run, it tells us where it is
through the YTGRAB_FFMPEG environment variable. That bundled copy is always
preferred; PATH is only a fallback for developers who already have FFmpeg
installed.
"""

import os
import shutil
from pathlib import Path

# Set by the launcher (or a developer) to point at a specific ffmpeg.exe.
# ytgrab itself never sets this and never writes to PATH or the registry.
_ENV_VAR = "YTGRAB_FFMPEG"


def find_ffmpeg() -> str | None:
    """Return a usable FFmpeg executable path, or None if none is available.

    Checks YTGRAB_FFMPEG first (a bundled/portable build), then PATH.
    """
    bundled = _bundled_ffmpeg()
    if bundled:
        return bundled
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def require_ffmpeg() -> str:
    """Return FFmpeg's path or raise a clear application error."""
    from ytgrab.core.errors import FfmpegMissingError

    path = find_ffmpeg()
    if path:
        return str(Path(path))
    raise FfmpegMissingError()


def _bundled_ffmpeg() -> str | None:
    """Return the path in YTGRAB_FFMPEG if it is set and points at a real file."""
    value = os.environ.get(_ENV_VAR)
    if not value:
        return None
    path = Path(value)
    return str(path) if path.is_file() else None
