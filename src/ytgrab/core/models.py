"""Application data models shared by the UI and core layers.

The models deliberately contain no yt-dlp or Tkinter types.  They are the
small, stable vocabulary used between the UI and the download core.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class VideoFormat:
    """One downloadable video stream."""

    format_id: str
    height: int
    fps: float | None
    ext: str
    codec: str | None
    has_audio: bool


@dataclass(frozen=True)
class AudioFormat:
    """One downloadable audio-only stream."""

    format_id: str
    ext: str
    bitrate_kbps: float | None
    codec: str | None


@dataclass(frozen=True)
class MediaInfo:
    """Everything the app needs to know about one video."""

    video_id: str
    title: str
    webpage_url: str
    uploader: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    video_formats: tuple[VideoFormat, ...] = ()
    audio_formats: tuple[AudioFormat, ...] = ()

    @property
    def resolutions(self) -> tuple[int, ...]:
        """Distinct video heights, highest first."""
        return tuple(sorted({f.height for f in self.video_formats}, reverse=True))

    @property
    def fps_values(self) -> tuple[float, ...]:
        """Distinct frame rates, highest first."""
        values = {f.fps for f in self.video_formats if f.fps is not None}
        return tuple(sorted(values, reverse=True))

    @property
    def has_audio(self) -> bool:
        """True if audio is available as a separate or muxed stream."""
        return bool(self.audio_formats) or any(
            f.has_audio for f in self.video_formats
        )


DownloadMode = Literal["video", "audio"]


@dataclass(frozen=True)
class DownloadRequest:
    """A single user-requested download."""

    url: str
    mode: DownloadMode
    output_folder: str
    video_height: int | None = None


@dataclass(frozen=True)
class ProgressEvent:
    """Progress reported by a running download."""

    stage: str
    percent: float | None = None
    speed: str | None = None
    eta: str | None = None


@dataclass(frozen=True)
class FinishedEvent:
    """Successful download result."""

    path: str


@dataclass(frozen=True)
class FailedEvent:
    """A failed download represented by an application-level error."""

    error: Exception
