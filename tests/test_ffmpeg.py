"""Tests for FFmpeg discovery."""

from ytgrab.core import ffmpeg
from ytgrab.core.errors import FfmpegMissingError


def test_find_ffmpeg_returns_path_from_shutil(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: "C:/ffmpeg.exe")
    assert ffmpeg.find_ffmpeg() == "C:/ffmpeg.exe"


def test_find_ffmpeg_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: None)
    assert ffmpeg.find_ffmpeg() is None


def test_require_ffmpeg_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg, "find_ffmpeg", lambda: None)
    try:
        ffmpeg.require_ffmpeg()
    except FfmpegMissingError as exc:
        assert "FFmpeg" in str(exc)
    else:
        raise AssertionError("FfmpegMissingError was not raised")


def test_find_ffmpeg_prefers_bundled_path_over_path_env(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "ffmpeg.exe"
    bundled.write_text("fake binary")
    monkeypatch.setenv("YTGRAB_FFMPEG", str(bundled))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: "C:/should-not-use.exe")
    assert ffmpeg.find_ffmpeg() == str(bundled)


def test_find_ffmpeg_ignores_bundled_env_var_if_file_missing(
    monkeypatch, tmp_path
) -> None:
    missing = tmp_path / "does-not-exist.exe"
    monkeypatch.setenv("YTGRAB_FFMPEG", str(missing))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: "C:/system-ffmpeg.exe")
    assert ffmpeg.find_ffmpeg() == "C:/system-ffmpeg.exe"


def test_find_ffmpeg_ignores_unset_bundled_env_var(monkeypatch) -> None:
    monkeypatch.setenv("YTGRAB_FFMPEG", "")
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: "C:/system-ffmpeg.exe")
    assert ffmpeg.find_ffmpeg() == "C:/system-ffmpeg.exe"
