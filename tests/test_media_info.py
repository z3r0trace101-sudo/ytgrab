"""Tests for the media information service using fake yt-dlp data."""

import pytest

from ytgrab.core.errors import ExtractionError, InvalidUrlError
from ytgrab.core.media_info import fetch_media_info, parse_media_info

VIDEO_ID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def sample_raw() -> dict:
    return {
        "_type": "video",
        "id": VIDEO_ID,
        "title": "Example title",
        "webpage_url": URL,
        "uploader": "Example channel",
        "duration": 125,
        "thumbnail": "https://example.test/thumb.jpg",
        "formats": [
            {
                "format_id": "137",
                "height": 1080,
                "fps": 30,
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "abr": 129,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
            },
            {
                "format_id": "sb0",
                "ext": "mhtml",
                "vcodec": "none",
                "acodec": "none",
            },
            {
                "format_id": "drm",
                "height": 720,
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "none",
                "has_drm": True,
            },
        ],
    }


def test_parse_media_info_maps_core_fields() -> None:
    info = parse_media_info(sample_raw())
    assert info.video_id == VIDEO_ID
    assert info.title == "Example title"
    assert info.uploader == "Example channel"
    assert info.duration_seconds == 125
    assert info.thumbnail_url.endswith("thumb.jpg")


def test_parse_media_info_splits_and_sorts_formats() -> None:
    info = parse_media_info(sample_raw())
    assert [item.format_id for item in info.video_formats] == ["137"]
    assert [item.format_id for item in info.audio_formats] == ["140"]
    assert info.resolutions == (1080,)
    assert info.has_audio


def test_parse_media_info_skips_drm_and_non_media_formats() -> None:
    info = parse_media_info(sample_raw())
    all_ids = [f.format_id for f in info.video_formats + info.audio_formats]
    assert "drm" not in all_ids
    assert "sb0" not in all_ids


def test_parse_media_info_falls_back_to_normalized_url() -> None:
    raw = sample_raw()
    raw.pop("webpage_url")
    info = parse_media_info(raw)
    assert info.webpage_url == URL


def test_parse_media_info_rejects_playlist_result() -> None:
    raw = sample_raw()
    raw["_type"] = "playlist"
    with pytest.raises(ExtractionError):
        parse_media_info(raw)


def test_parse_media_info_rejects_missing_title() -> None:
    raw = sample_raw()
    raw.pop("title")
    with pytest.raises(ExtractionError):
        parse_media_info(raw)


def test_parse_media_info_rejects_no_usable_formats() -> None:
    raw = sample_raw()
    raw["formats"] = []
    with pytest.raises(ExtractionError):
        parse_media_info(raw)


def test_parse_media_info_ignores_bad_optional_values() -> None:
    raw = sample_raw()
    raw["duration"] = -1
    raw["uploader"] = "   "
    raw["channel"] = "Channel fallback"
    info = parse_media_info(raw)
    assert info.duration_seconds is None
    assert info.uploader == "Channel fallback"


def test_fetch_media_info_validates_before_extractor() -> None:
    calls: list[str] = []

    def extractor(url: str) -> dict:
        calls.append(url)
        return sample_raw()

    with pytest.raises(InvalidUrlError):
        fetch_media_info("https://example.com", extractor=extractor)
    assert calls == []


def test_fetch_media_info_passes_only_normalized_url() -> None:
    calls: list[str] = []

    def extractor(url: str) -> dict:
        calls.append(url)
        return sample_raw()

    info = fetch_media_info(
        f"https://youtu.be/{VIDEO_ID}?list=abc&t=10", extractor=extractor
    )
    assert info.video_id == VIDEO_ID
    assert calls == [URL]
