"""The media information service: URL -> yt-dlp -> MediaInfo.

Public API:
    fetch_media_info(url)      the function the app calls
    parse_media_info(raw)      converts yt-dlp's raw dictionary to MediaInfo

This module knows the *shape* of yt-dlp's dictionaries but never imports
yt_dlp itself. Only core/downloader.py talks to yt-dlp. Nothing is downloaded.
"""

from collections.abc import Callable, Mapping
from typing import Any

from ytgrab.core.downloader import extract_raw_info
from ytgrab.core.errors import ExtractionError, InvalidUrlError
from ytgrab.core.models import AudioFormat, MediaInfo, VideoFormat
from ytgrab.core.url_validation import build_normalized_url, validate_youtube_url

# Anything that turns a URL into yt-dlp-style raw data. Tests pass a fake one.
RawInfoExtractor = Callable[[str], Mapping[str, Any]]

# yt-dlp writes "none" as the codec when a stream has no video/audio track.
_NO_CODEC = "none"


def fetch_media_info(
    url: str,
    extractor: RawInfoExtractor = extract_raw_info,
) -> MediaInfo:
    """Look up a YouTube video and return its information.

    Raises a YtGrabError subclass on failure (InvalidUrlError, NetworkError,
    VideoUnavailableError, VideoRestrictedError, ExtractionError or
    UnexpectedError). Nothing is downloaded.
    """
    validation = validate_youtube_url(url)
    if not validation.is_valid or validation.normalized_url is None:
        raise InvalidUrlError(validation.error)

    # The normalized URL has no playlist or tracking parameters.
    raw = extractor(validation.normalized_url)
    return parse_media_info(raw)


def parse_media_info(raw: Mapping[str, Any]) -> MediaInfo:
    """Convert yt-dlp's raw dictionary into a MediaInfo.

    Missing optional fields become None; formats that are not real downloadable
    audio/video streams are skipped. Raises ExtractionError if the data is too
    malformed to use.
    """
    result_type = raw.get("_type")
    if result_type not in (None, "video"):
        raise ExtractionError(detail=f"Unexpected result type: {result_type!r}")

    video_id = _text(raw.get("id"))
    title = _text(raw.get("title"))
    if video_id is None or title is None:
        raise ExtractionError(detail="Result is missing a valid 'id' or 'title'")

    video_formats, audio_formats = _parse_formats(raw.get("formats"))
    if not video_formats and not audio_formats:
        raise ExtractionError(detail="No usable audio or video formats were found")

    return MediaInfo(
        video_id=video_id,
        title=title,
        webpage_url=_text(raw.get("webpage_url")) or build_normalized_url(video_id),
        uploader=_text(raw.get("uploader")) or _text(raw.get("channel")),
        duration_seconds=_positive_int(raw.get("duration")),
        thumbnail_url=_text(raw.get("thumbnail")),
        video_formats=tuple(video_formats),
        audio_formats=tuple(audio_formats),
    )


def _parse_formats(entries: object) -> tuple[list[VideoFormat], list[AudioFormat]]:
    """Split yt-dlp's format list into video and audio formats, best first."""
    videos: list[VideoFormat] = []
    audios: list[AudioFormat] = []
    if isinstance(entries, list | tuple):
        for entry in entries:
            parsed = _parse_format(entry)
            if isinstance(parsed, VideoFormat):
                videos.append(parsed)
            elif isinstance(parsed, AudioFormat):
                audios.append(parsed)
    videos.sort(key=lambda f: (f.height, f.fps or 0.0), reverse=True)
    audios.sort(key=lambda f: f.bitrate_kbps or 0.0, reverse=True)
    return videos, audios


def _parse_format(entry: object) -> VideoFormat | AudioFormat | None:
    """Convert one raw format, or return None if it is not a usable stream.

    Skipped: non-dictionaries, DRM-protected formats, formats without an id or
    container, and things like storyboards (no video and no audio track).
    """
    if not isinstance(entry, Mapping) or entry.get("has_drm") is True:
        return None

    format_id = _text(entry.get("format_id"))
    ext = _text(entry.get("ext"))
    if format_id is None or ext is None:
        return None

    vcodec = _text(entry.get("vcodec"))
    acodec = _text(entry.get("acodec"))
    has_audio_track = acodec not in (None, _NO_CODEC)
    height = _positive_int(entry.get("height"))

    if vcodec != _NO_CODEC and height is not None:
        return VideoFormat(
            format_id=format_id,
            height=height,
            fps=_positive_number(entry.get("fps")),
            ext=ext,
            codec=vcodec,
            has_audio=has_audio_track,
        )
    if vcodec in (None, _NO_CODEC) and has_audio_track:
        return AudioFormat(
            format_id=format_id,
            ext=ext,
            bitrate_kbps=_positive_number(entry.get("abr")),
            codec=acodec,
        )
    return None


def _text(value: object) -> str | None:
    """A non-empty stripped string, or None."""
    if isinstance(value, str):
        return value.strip() or None
    return None


def _positive_number(value: object) -> float | None:
    """A number greater than zero, or None. Booleans and strings are rejected."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _positive_int(value: object) -> int | None:
    number = _positive_number(value)
    return int(number) if number is not None else None
