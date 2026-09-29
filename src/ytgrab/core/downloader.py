"""The single yt-dlp integration boundary.

Only this module imports yt_dlp.  The rest of the application works with our
own models and error classes.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ytgrab.core.errors import (
    ExtractionError,
    FfmpegMissingError,
    InvalidUrlError,
    NetworkError,
    OutputError,
    UnexpectedError,
    VideoRestrictedError,
    VideoUnavailableError,
    YtGrabError,
)
from ytgrab.core.ffmpeg import require_ffmpeg
from ytgrab.core.models import (
    DownloadRequest,
    FinishedEvent,
    ProgressEvent,
)
from ytgrab.core.url_validation import validate_youtube_url

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[ProgressEvent], None]

_RESTRICTED_MARKERS = (
    "private video",
    "video is private",
    "sign in",
    "confirm your age",
    "age-restricted",
    "age restricted",
    "members-only",
    "members only",
    "join this channel",
    "in your country",
    "not made this video available",
    "requires payment",
)
_UNAVAILABLE_MARKERS = (
    "video unavailable",
    "video is unavailable",
    "video is not available",
    "no longer available",
    "has been removed",
    "has been terminated",
    "does not exist",
)
_NETWORK_MARKERS = (
    "urlopen error",
    "getaddrinfo failed",
    "name or service not known",
    "name resolution",
    "network is unreachable",
    "no route to host",
    "unable to connect",
    "timed out",
    "connection reset",
    "connection refused",
)
_OUTPUT_MARKERS = (
    "permission denied",
    "permissionerror",
    "no space left on device",
    "read-only file system",
    "invalid argument",
    "file name too long",
)
_FFMPEG_MARKERS = (
    "ffmpeg not found",
    "ffmpeg is not installed",
    "unable to find ffmpeg",
    "ffmpeg executable",
)
_MAX_CAUSE_DEPTH = 5


class _YtdlpLogger:
    """Forward yt-dlp messages to the application's logging system."""

    def debug(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        logger.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        logger.debug("yt-dlp error: %s", msg)


def _metadata_options() -> dict[str, Any]:
    return {
        "logger": _YtdlpLogger(),
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
    }


def extract_raw_info(url: str) -> dict[str, Any]:
    """Fetch metadata only and return yt-dlp's raw dictionary."""
    import yt_dlp
    from yt_dlp.utils import DownloadError

    logger.info("Fetching media information")
    try:
        with yt_dlp.YoutubeDL(_metadata_options()) as ydl:
            raw = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        error = _translate_download_error(exc)
        logger.warning(
            "Media information request failed (%s): %s",
            type(error).__name__,
            error.detail,
        )
        raise error from exc
    except Exception as exc:
        logger.exception("Unexpected error while fetching media information")
        raise UnexpectedError(detail=f"{type(exc).__name__}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ExtractionError(
            detail=f"yt-dlp returned {type(raw).__name__} instead of a dictionary"
        )
    return raw


def download_media(
    request: DownloadRequest,
    on_progress: ProgressCallback | None = None,
) -> FinishedEvent:
    """Download one video or audio file and report progress through a callback."""
    validation = validate_youtube_url(request.url)
    if not validation.is_valid or validation.normalized_url is None:
        raise InvalidUrlError(validation.error)

    output_folder = Path(request.output_folder).expanduser()
    _validate_output_folder(output_folder)
    ffmpeg_path = require_ffmpeg()

    options = _download_options(request, on_progress, ffmpeg_path)
    import yt_dlp
    from yt_dlp.utils import DownloadError

    logger.info("Starting %s download", request.mode)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(validation.normalized_url, download=True)
            path = _find_final_path(ydl, info, output_folder, request.mode)
    except YtGrabError:
        raise
    except DownloadError as exc:
        error = _translate_download_error(exc)
        logger.warning(
            "Download failed (%s): %s", type(error).__name__, error.detail
        )
        raise error from exc
    except OSError as exc:
        logger.warning("Output operation failed: %s", exc)
        raise OutputError(detail=f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during download")
        raise UnexpectedError(detail=f"{type(exc).__name__}: {exc}") from exc

    if on_progress:
        on_progress(ProgressEvent("Finished", 100.0))
    return FinishedEvent(str(path))


def _download_options(
    request: DownloadRequest,
    on_progress: ProgressCallback | None,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    folder = str(Path(request.output_folder).resolve())
    if request.mode == "audio":
        format_selector = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
        merge_format = None
    else:
        if request.video_height:
            limit = request.video_height
            format_selector = (
                f"bestvideo[height<={limit}]+bestaudio/"
                f"best[height<={limit}]/best"
            )
        else:
            format_selector = "bestvideo+bestaudio/best"
        postprocessors = []
        merge_format = "mp4"

    options: dict[str, Any] = {
        "logger": _YtdlpLogger(),
        "quiet": True,
        "noplaylist": True,
        "format": format_selector,
        "outtmpl": str(Path(folder) / "%(title)s [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "postprocessors": postprocessors,
    }
    if ffmpeg_path:
        # Tell yt-dlp exactly which FFmpeg to use, so it never has to search
        # PATH itself. This is what lets a portable/bundled FFmpeg work.
        options["ffmpeg_location"] = ffmpeg_path
    if merge_format:
        options["merge_output_format"] = merge_format
    if on_progress:
        options["progress_hooks"] = [
            lambda data: _handle_progress(data, on_progress, request.mode)
        ]
        options["postprocessor_hooks"] = [
            lambda data: on_progress(ProgressEvent("Processing…"))
        ]
    return options


def _handle_progress(
    data: dict[str, Any], callback: ProgressCallback, mode: str = "video"
) -> None:
    status = data.get("status")
    if status == "finished":
        callback(ProgressEvent("Processing…", 100.0))
        return
    if status != "downloading":
        return

    downloaded = data.get("downloaded_bytes")
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    percent = None
    if isinstance(downloaded, int | float) and isinstance(total, int | float) and total:
        percent = max(0.0, min(100.0, downloaded * 100 / total))

    stage = "Downloading audio…" if mode == "audio" else "Downloading video…"
    callback(
        ProgressEvent(
            stage=stage,
            percent=percent,
            speed=_format_speed(data.get("speed")),
            eta=_format_eta(data.get("eta")),
        )
    )


def _format_speed(value: object) -> str | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    units = ("B/s", "KiB/s", "MiB/s", "GiB/s")
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}"
        number /= 1024
    return None


def _format_eta(value: object) -> str | None:
    if not isinstance(value, int | float) or value < 0:
        return None
    seconds = int(value)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _find_final_path(
    ydl: Any,
    info: dict[str, Any],
    folder: Path,
    mode: str,
) -> Path:
    for key in ("filepath", "_filename"):
        value = info.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if path.exists():
                return path.resolve()

    try:
        prepared = Path(ydl.prepare_filename(info))
    except Exception:
        prepared = folder / "download"
    extension = ".mp3" if mode == "audio" else ".mp4"
    candidate = prepared.with_suffix(extension)
    if candidate.exists():
        return candidate.resolve()

    matches = sorted(folder.glob(f"* [{info.get('id', '')}]*"))
    if matches:
        return matches[-1].resolve()
    raise OutputError(detail=f"Downloaded file could not be located in {folder}")


def _validate_output_folder(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".ytgrab-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise OutputError(detail=f"{type(exc).__name__}: {exc}") from exc


def _translate_download_error(exc: Any) -> YtGrabError:
    detail = str(exc)
    text = detail.lower()
    if _contains_any(text, _FFMPEG_MARKERS) and (
        "not found" in text or "not installed" in text or "ffmpeg" in text
    ):
        return FfmpegMissingError(detail=detail)
    if _contains_any(text, _OUTPUT_MARKERS):
        return OutputError(detail=detail)
    if _contains_any(text, _RESTRICTED_MARKERS):
        return VideoRestrictedError(detail=detail)
    if _contains_any(text, _UNAVAILABLE_MARKERS):
        return VideoUnavailableError(detail=detail)
    if _contains_any(text, _NETWORK_MARKERS) or _has_os_error_cause(exc):
        return NetworkError(detail=detail)
    return ExtractionError(detail=detail)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _has_os_error_cause(exc: Any) -> bool:
    exc_info = getattr(exc, "exc_info", None)
    current = exc_info[1] if isinstance(exc_info, tuple) and len(exc_info) > 1 else None
    for _ in range(_MAX_CAUSE_DEPTH):
        if current is None:
            return False
        if isinstance(current, OSError):
            return True
        current = getattr(current, "cause", None) or current.__cause__
    return False
