"""Tests for ytgrab.core.url_validation."""

import pytest

from ytgrab.core.url_validation import (
    UrlValidationResult,
    build_normalized_url,
    extract_video_id,
    validate_youtube_url,
)

# A realistic 11-character video ID, plus a second one for variety.
VIDEO_ID = "dQw4w9WgXcQ"
NORMALIZED = f"https://www.youtube.com/watch?v={VIDEO_ID}"


# --- Valid URLs -------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://youtube.com/shorts/{VIDEO_ID}",
        f"https://m.youtube.com/shorts/{VIDEO_ID}",
    ],
)
def test_valid_video_urls(url: str) -> None:
    result = validate_youtube_url(url)
    assert result.is_valid
    assert result.video_id == VIDEO_ID
    assert result.normalized_url == NORMALIZED
    assert result.error is None


def test_playlist_parameters_are_ignored() -> None:
    url = f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PLabc123&index=4"
    result = validate_youtube_url(url)
    assert result.is_valid
    assert result.normalized_url == NORMALIZED
    assert "list" not in result.normalized_url


def test_extra_query_parameters_are_ignored() -> None:
    url = f"https://www.youtube.com/watch?feature=share&v={VIDEO_ID}&t=42s&si=xyz"
    result = validate_youtube_url(url)
    assert result.is_valid
    assert result.video_id == VIDEO_ID
    assert result.normalized_url == NORMALIZED


def test_short_link_with_tracking_parameters() -> None:
    result = validate_youtube_url(f"https://youtu.be/{VIDEO_ID}?si=abc&t=10")
    assert result.is_valid
    assert result.normalized_url == NORMALIZED


def test_shorts_url_with_trailing_slash_and_query() -> None:
    url = f"https://www.youtube.com/shorts/{VIDEO_ID}/?feature=share"
    result = validate_youtube_url(url)
    assert result.is_valid
    assert result.video_id == VIDEO_ID


def test_http_is_accepted_but_normalized_to_https() -> None:
    result = validate_youtube_url(f"http://www.youtube.com/watch?v={VIDEO_ID}")
    assert result.is_valid
    assert result.normalized_url is not None
    assert result.normalized_url.startswith("https://")


def test_surrounding_whitespace_is_stripped() -> None:
    result = validate_youtube_url(f"  \n https://youtu.be/{VIDEO_ID}\t ")
    assert result.is_valid
    assert result.video_id == VIDEO_ID


def test_host_and_scheme_are_case_insensitive() -> None:
    result = validate_youtube_url(f"HTTPS://WWW.YouTube.COM/watch?v={VIDEO_ID}")
    assert result.is_valid
    assert result.video_id == VIDEO_ID


def test_video_id_is_case_sensitive() -> None:
    # IDs are case-sensitive on YouTube, so we must not change their case.
    result = validate_youtube_url("https://youtu.be/AbCdEfGhIjK")
    assert result.video_id == "AbCdEfGhIjK"


def test_ids_with_dash_and_underscore_are_valid() -> None:
    result = validate_youtube_url("https://youtu.be/a-b_c-d_e-f")
    assert result.is_valid
    assert result.video_id == "a-b_c-d_e-f"


def test_different_forms_normalize_to_the_same_url() -> None:
    urls = [
        f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PL1",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=5",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
    ]
    assert {validate_youtube_url(u).normalized_url for u in urls} == {NORMALIZED}


# --- Invalid URLs -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # Empty / not a URL
        "",
        "   ",
        "\n\t",
        "hello world",
        "not a url",
        # Wrong sites
        "https://google.com",
        "https://example.com",
        f"https://example.com/watch?v={VIDEO_ID}",
        # Lookalike hosts (why a simple "youtube.com in url" check is not enough)
        f"https://youtube.com.example.com/watch?v={VIDEO_ID}",
        f"https://example.com/youtube.com/watch?v={VIDEO_ID}",
        f"https://notyoutube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com.evil.io/{VIDEO_ID}",
        f"https://example.com/?u=https://youtube.com/watch?v={VIDEO_ID}",
        # Sneaky authority section
        f"https://youtube.com@evil.com/watch?v={VIDEO_ID}",
        f"https://user:pass@www.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com:8080/watch?v={VIDEO_ID}",
        # Unsupported schemes
        "javascript:alert(1)",
        f"javascript://www.youtube.com/watch?v={VIDEO_ID}",
        f"file:///C:/videos/watch?v={VIDEO_ID}",
        f"ftp://www.youtube.com/watch?v={VIDEO_ID}",
        f"//www.youtube.com/watch?v={VIDEO_ID}",
        f"www.youtube.com/watch?v={VIDEO_ID}",
        # Malformed
        "https://",
        "http://[invalid",
        f"https://www.youtube.com/watch?v={VIDEO_ID} extra",
        # Right host, wrong kind of page
        "https://www.youtube.com/",
        "https://www.youtube.com/@SomeChannel",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        "https://www.youtube.com/results?search_query=cats",
        "https://www.youtube.com/playlist?list=PLabc123",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?list=PLabc123",
        "https://youtu.be/",
        f"https://www.youtube.com/watch/{VIDEO_ID}",
        f"https://www.youtube.com/shorts//{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}/extra",
        # Bad video IDs
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=waytoolongvideoid",
        "https://www.youtube.com/watch?v=bad!chars!!",
        "https://youtu.be/short",
    ],
)
def test_invalid_urls(url: str) -> None:
    result = validate_youtube_url(url)
    assert not result.is_valid
    assert result.video_id is None
    assert result.normalized_url is None
    assert result.error


# --- Small helpers and result shape -----------------------------------------


def test_invalid_result_has_a_user_friendly_error() -> None:
    result = validate_youtube_url("https://example.com")
    assert result.error == "That doesn't look like a link to a YouTube video."


def test_extract_video_id_returns_none_for_invalid_input() -> None:
    assert extract_video_id("nonsense") is None
    assert extract_video_id(f"https://youtu.be/{VIDEO_ID}") == VIDEO_ID


def test_build_normalized_url() -> None:
    assert build_normalized_url(VIDEO_ID) == NORMALIZED


def test_result_is_immutable() -> None:
    result = validate_youtube_url(f"https://youtu.be/{VIDEO_ID}")
    assert isinstance(result, UrlValidationResult)
    with pytest.raises(AttributeError):
        result.is_valid = False  # type: ignore[misc]
