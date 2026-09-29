"""Behavioral tests for application-level errors."""

import pytest

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
from ytgrab.core.url_validation import validate_youtube_url

ERROR_TYPES = (
    InvalidUrlError,
    NetworkError,
    VideoUnavailableError,
    VideoRestrictedError,
    ExtractionError,
    FfmpegMissingError,
    OutputError,
    UnexpectedError,
)


def test_base_error_uses_default_message() -> None:
    error = YtGrabError()
    assert str(error) == YtGrabError.user_message
    assert error.user_message == YtGrabError.user_message


def test_custom_message_replaces_default_for_one_instance() -> None:
    error = YtGrabError("custom")
    assert str(error) == "custom"
    assert error.user_message == "custom"


def test_custom_message_does_not_change_class_default() -> None:
    YtGrabError("custom")
    assert YtGrabError().user_message == (
        "Something went wrong. Details were saved to the log."
    )


def test_empty_message_uses_default() -> None:
    assert str(YtGrabError("")) == YtGrabError.user_message


def test_detail_defaults_to_none() -> None:
    assert YtGrabError().detail is None


def test_detail_is_hidden_from_user_message() -> None:
    error = YtGrabError("Friendly message", detail="secret technical detail")
    assert error.detail == "secret technical detail"
    assert str(error) == "Friendly message"
    assert "secret technical detail" not in error.user_message


def test_detail_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        YtGrabError("message", "detail")  # type: ignore[call-arg]


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_all_error_types_inherit_from_base(error_type: type[YtGrabError]) -> None:
    assert issubclass(error_type, YtGrabError)


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_all_error_types_have_nonempty_messages(
    error_type: type[YtGrabError],
) -> None:
    error = error_type()
    assert error.user_message
    assert str(error) == error.user_message


def test_all_default_messages_are_distinct() -> None:
    messages = [YtGrabError.user_message, *(t.user_message for t in ERROR_TYPES)]
    assert len(messages) == len(set(messages))


def test_child_accepts_custom_message_and_detail() -> None:
    error = NetworkError("temporary", detail="socket reset")
    assert str(error) == "temporary"
    assert error.detail == "socket reset"


def test_child_can_be_caught_as_base_without_losing_detail() -> None:
    with pytest.raises(YtGrabError) as caught:
        raise NetworkError(detail="connection reset")
    assert isinstance(caught.value, NetworkError)
    assert caught.value.detail == "connection reset"


def test_sibling_errors_are_not_each_other() -> None:
    with pytest.raises(NetworkError):
        raise NetworkError()
    with pytest.raises(VideoUnavailableError):
        raise VideoUnavailableError()


def test_invalid_url_message_matches_validator() -> None:
    result = validate_youtube_url("https://example.com")
    error = InvalidUrlError(result.error)
    assert error.user_message == result.error
