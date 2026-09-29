"""Tests for the application's immutable data models."""

import pytest

from ytgrab.core.models import (
    AudioFormat,
    DownloadRequest,
    FinishedEvent,
    MediaInfo,
    ProgressEvent,
    VideoFormat,
)


def _video(height: int, fps: float | None, audio: bool = False) -> VideoFormat:
    return VideoFormat(str(height), height, fps, "mp4", "avc1", audio)


def test_media_info_resolutions_are_distinct_and_descending() -> None:
    info = MediaInfo(
        "abc",
        "title",
        "https://youtube.com/watch?v=abc",
        video_formats=(_video(720, 30), _video(1080, 60), _video(720, 60)),
    )
    assert info.resolutions == (1080, 720)


def test_media_info_fps_values_are_distinct_and_descending() -> None:
    info = MediaInfo(
        "abc",
        "title",
        "https://youtube.com/watch?v=abc",
        video_formats=(_video(720, 30), _video(1080, 60), _video(480, 30)),
    )
    assert info.fps_values == (60.0, 30.0)


def test_media_info_has_audio_for_audio_format() -> None:
    audio = AudioFormat("140", "m4a", 128.0, "mp4a")
    info = MediaInfo("abc", "title", "url", audio_formats=(audio,))
    assert info.has_audio


def test_media_info_has_audio_for_muxed_video() -> None:
    info = MediaInfo(
        "abc", "title", "url", video_formats=(_video(720, 30, audio=True),)
    )
    assert info.has_audio


def test_media_models_are_frozen() -> None:
    info = MediaInfo("abc", "title", "url")
    with pytest.raises(AttributeError):
        info.title = "changed"  # type: ignore[misc]


def test_download_request_stores_video_height() -> None:
    request = DownloadRequest("url", "video", "C:/Downloads", 1080)
    assert request.mode == "video"
    assert request.video_height == 1080


def test_progress_event_allows_unknown_percent() -> None:
    event = ProgressEvent("Processing…")
    assert event.percent is None


def test_finished_event_stores_path() -> None:
    event = FinishedEvent("C:/Downloads/file.mp4")
    assert event.path.endswith("file.mp4")
