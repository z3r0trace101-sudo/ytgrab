"""Tests for the yt-dlp adapter without network access."""

import sys
import types

from ytgrab.core import downloader
from ytgrab.core.downloader import (
    _download_options,
    _format_eta,
    _format_speed,
    _handle_progress,
    _translate_download_error,
)
from ytgrab.core.errors import (
    ExtractionError,
    NetworkError,
    OutputError,
    VideoRestrictedError,
    VideoUnavailableError,
)
from ytgrab.core.models import DownloadRequest, ProgressEvent


class FakeDownloadError(Exception):
    exc_info = None


def error(message: str) -> FakeDownloadError:
    return FakeDownloadError(message)


def test_error_translation_classifies_restricted() -> None:
    assert isinstance(
        _translate_download_error(error("Video is private")), VideoRestrictedError
    )


def test_error_translation_classifies_unavailable() -> None:
    assert isinstance(
        _translate_download_error(error("Video unavailable")), VideoUnavailableError
    )


def test_error_translation_classifies_network() -> None:
    assert isinstance(
        _translate_download_error(error("Connection reset by peer")), NetworkError
    )


def test_error_translation_classifies_output_failure() -> None:
    assert isinstance(
        _translate_download_error(error("Permission denied")), OutputError
    )


def test_error_translation_falls_back_to_extraction() -> None:
    assert isinstance(
        _translate_download_error(error("Unknown extractor failure")), ExtractionError
    )


def test_download_options_for_best_video() -> None:
    request = DownloadRequest("url", "video", "C:/Downloads")
    options = _download_options(request, None)
    assert options["noplaylist"] is True
    assert options["format"] == "bestvideo+bestaudio/best"
    assert options["merge_output_format"] == "mp4"
    assert options["postprocessors"] == []


def test_download_options_for_selected_height() -> None:
    request = DownloadRequest("url", "video", "C:/Downloads", 720)
    options = _download_options(request, None)
    assert "height<=720" in options["format"]


def test_download_options_for_audio() -> None:
    request = DownloadRequest("url", "audio", "C:/Downloads")
    options = _download_options(request, None)
    assert options["format"] == "bestaudio/best"
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"


def test_format_helpers() -> None:
    assert _format_speed(1024) == "1.0 KiB/s"
    assert _format_speed(1024 * 1024) == "1.0 MiB/s"
    assert _format_speed(0) is None
    assert _format_eta(65) == "1:05"
    assert _format_eta(3665) == "1:01:05"
    assert _format_eta(-1) is None


def test_progress_hook_maps_download_data() -> None:
    events: list[ProgressEvent] = []
    _handle_progress(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 1024,
            "eta": 5,
        },
        events.append,
        "video",
    )
    assert events == [
        ProgressEvent("Downloading video…", 50.0, "1.0 KiB/s", "0:05")
    ]


def test_progress_hook_ignores_other_statuses() -> None:
    events: list[ProgressEvent] = []
    _handle_progress({"status": "error"}, events.append, "video")
    assert events == []


def test_progress_hook_finished_enters_processing() -> None:
    events: list[ProgressEvent] = []
    _handle_progress({"status": "finished"}, events.append, "video")
    assert events == [ProgressEvent("Processing…", 100.0)]


def test_download_media_uses_normalized_url_with_fake_ytdlp(monkeypatch, tmp_path):
    import ytgrab.core.downloader as downloader

    captured: dict[str, object] = {}

    class FakeDownloadError(Exception):
        exc_info = None

    class FakeYDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            captured["url"] = url
            captured["download"] = download
            path = tmp_path / "Example [dQw4w9WgXcQ].mp4"
            path.write_bytes(b"test")
            return {"id": "dQw4w9WgXcQ", "title": "Example", "filepath": str(path)}

        def prepare_filename(self, info):
            return str(tmp_path / "Example [dQw4w9WgXcQ].mp4")

    fake_module = types.ModuleType("yt_dlp")
    fake_module.YoutubeDL = FakeYDL
    fake_utils = types.ModuleType("yt_dlp.utils")
    fake_utils.DownloadError = FakeDownloadError
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", fake_utils)
    monkeypatch.setattr(downloader, "require_ffmpeg", lambda: "ffmpeg")

    request = DownloadRequest(
        "https://youtu.be/dQw4w9WgXcQ?list=abc&t=10",
        "video",
        str(tmp_path),
    )
    events: list[ProgressEvent] = []
    result = downloader.download_media(request, events.append)

    assert captured["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert captured["download"] is True
    assert result.path.endswith("Example [dQw4w9WgXcQ].mp4")
    assert events[-1] == ProgressEvent("Finished", 100.0)


def test_download_options_passes_ffmpeg_location_when_given() -> None:
    request = DownloadRequest("https://youtu.be/x", "video", "C:/downloads")
    options = _download_options(request, None, "C:/bundled/ffmpeg.exe")
    assert options["ffmpeg_location"] == "C:/bundled/ffmpeg.exe"


def test_download_options_omits_ffmpeg_location_when_not_given() -> None:
    request = DownloadRequest("https://youtu.be/x", "video", "C:/downloads")
    options = _download_options(request, None)
    assert "ffmpeg_location" not in options


def test_download_media_passes_resolved_ffmpeg_path_to_options(
    monkeypatch, tmp_path
) -> None:
    """download_media must pass require_ffmpeg()'s result into yt-dlp options,
    so a bundled/portable FFmpeg (found via YTGRAB_FFMPEG) is actually used."""
    seen_options: dict = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            seen_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            path = tmp_path / "Example [dQw4w9WgXcQ].mp4"
            path.write_text("data")
            return {"id": "dQw4w9WgXcQ", "filepath": str(path)}

        def prepare_filename(self, info):
            return str(tmp_path / "Example [dQw4w9WgXcQ].mp4")

    fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
    fake_utils = types.SimpleNamespace(DownloadError=Exception)
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", fake_utils)
    monkeypatch.setattr(
        downloader, "require_ffmpeg", lambda: "C:/bundled/ffmpeg.exe"
    )

    request = DownloadRequest(
        "https://youtu.be/dQw4w9WgXcQ", "video", str(tmp_path)
    )
    downloader.download_media(request)

    assert seen_options["ffmpeg_location"] == "C:/bundled/ffmpeg.exe"
