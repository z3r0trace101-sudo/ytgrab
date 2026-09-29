"""YouTube URL validation.

Pure string/URL logic: no network access, no yt-dlp, no GUI. It answers one
question: "Is this text a link to a single YouTube video, and if so, which one?"

Usage:

    result = validate_youtube_url("https://youtu.be/dQw4w9WgXcQ?si=abc")
    if result.is_valid:
        print(result.video_id)        # dQw4w9WgXcQ
        print(result.normalized_url)  # https://www.youtube.com/watch?v=dQw4w9WgXcQ
    else:
        print(result.error)           # short message suitable for the UI
"""

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qs, urlsplit

# Only these hostnames are accepted. Exact matches only, so lookalikes such as
# "youtube.com.example.com" are rejected.
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
_SHORT_LINK_HOST = "youtu.be"

# https is preferred; http is accepted only because people sometimes paste old
# links. The normalized URL is always https.
_ALLOWED_SCHEMES = frozenset({"https", "http"})

# A YouTube video ID is exactly 11 characters: letters, digits, "-" and "_".
_VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")

_INVALID_MESSAGE = "That doesn't look like a link to a YouTube video."


@dataclass(frozen=True)
class UrlValidationResult:
    """The outcome of validating a URL.

    If ``is_valid`` is True, ``video_id`` and ``normalized_url`` are set and
    ``error`` is None. Otherwise ``error`` holds a short user-facing message and
    the other two are None.
    """

    is_valid: bool
    video_id: str | None = None
    normalized_url: str | None = None
    error: str | None = None


def validate_youtube_url(url: str) -> UrlValidationResult:
    """Check whether ``url`` points to a single YouTube video.

    Accepted forms (http or https; playlist and tracking parameters ignored):
      - youtube.com/watch?v=ID   (also www. and m.)
      - youtu.be/ID
      - youtube.com/shorts/ID    (also www. and m.)
    """
    video_id = extract_video_id(url)
    if video_id is None:
        return UrlValidationResult(is_valid=False, error=_INVALID_MESSAGE)
    return UrlValidationResult(
        is_valid=True,
        video_id=video_id,
        normalized_url=build_normalized_url(video_id),
    )


def extract_video_id(url: str) -> str | None:
    """Return the video ID from a supported YouTube URL, or None if unsupported."""
    parts = _split_url(url)
    if parts is None:
        return None

    host = parts.hostname  # lowercased; excludes any port or user info
    path = parts.path

    if host == _SHORT_LINK_HOST:
        candidate = _id_from_short_link_path(path)
    elif host in _YOUTUBE_HOSTS:
        candidate = _id_from_youtube_path(path, parts.query)
    else:
        return None

    if candidate is not None and _VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate
    return None


def build_normalized_url(video_id: str) -> str:
    """Build the one canonical URL we use for a video ID."""
    return f"https://www.youtube.com/watch?v={video_id}"


def _split_url(url: str) -> SplitResult | None:
    """Parse ``url`` and reject anything that is not a plain http(s) URL."""
    text = url.strip()
    if not text or any(char.isspace() for char in text):
        return None

    try:
        parts = urlsplit(text)
        port = parts.port  # raises ValueError if the port is invalid
    except ValueError:
        return None

    if parts.scheme not in _ALLOWED_SCHEMES:
        return None
    if not parts.hostname:
        return None
    # Real YouTube links never contain a port or "user:password@". Refusing
    # them blocks tricks like https://youtube.com@evil.com/.
    if port is not None or parts.username is not None or parts.password is not None:
        return None
    return parts


def _id_from_short_link_path(path: str) -> str | None:
    """youtu.be links look like /ID."""
    segments = _path_segments(path)
    if len(segments) == 1:
        return segments[0]
    return None


def _id_from_youtube_path(path: str, query: str) -> str | None:
    """Handle /watch?v=ID and /shorts/ID on youtube.com hosts."""
    segments = _path_segments(path)
    if segments == ["watch"]:
        values = parse_qs(query).get("v")
        return values[0] if values else None
    if len(segments) == 2 and segments[0] == "shorts":
        return segments[1]
    return None


def _path_segments(path: str) -> list[str]:
    """Split a URL path into segments, ignoring one optional trailing slash.

    "/shorts/abc/" -> ["shorts", "abc"]. Empty segments elsewhere (as in
    "/shorts//abc") are kept, so such odd paths fail to match and are rejected.
    """
    if path.endswith("/"):
        path = path[:-1]
    return path.split("/")[1:]
