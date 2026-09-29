"""Application-level errors shown to the UI and recorded in logs."""


class YtGrabError(Exception):
    """Base class for every expected error ytgrab reports to the UI."""

    user_message: str = "Something went wrong. Details were saved to the log."

    def __init__(
        self,
        user_message: str | None = None,
        *,
        detail: str | None = None,
    ) -> None:
        if user_message:
            self.user_message = user_message
        self.detail = detail
        super().__init__(self.user_message)


class InvalidUrlError(YtGrabError):
    """The text is not a supported YouTube video URL."""

    user_message = "That doesn't look like a link to a YouTube video."


class NetworkError(YtGrabError):
    """The internet connection failed or YouTube could not be reached."""

    user_message = (
        "Couldn't connect to YouTube. Check your internet connection and try again."
    )


class VideoUnavailableError(YtGrabError):
    """The video does not exist any more or is not available."""

    user_message = "This video is unavailable. It may have been removed or deleted."


class VideoRestrictedError(YtGrabError):
    """The video is private or otherwise restricted."""

    user_message = (
        "This video is private or restricted (for example age-restricted, "
        "members-only, or blocked in your region), so it can't be accessed."
    )


class ExtractionError(YtGrabError):
    """yt-dlp could not read or understand the video's information."""

    user_message = (
        "Couldn't read this video's information. YouTube may have changed "
        "something; updating yt-dlp often fixes this."
    )


class FfmpegMissingError(YtGrabError):
    """FFmpeg is required for the requested output."""

    user_message = (
        "FFmpeg is required to create the requested file. Install FFmpeg and "
        "make sure it is available on PATH, then try again."
    )


class OutputError(YtGrabError):
    """The selected output folder cannot be written to."""

    user_message = (
        "Couldn't save the file to that folder. Check the folder permissions "
        "and available disk space."
    )


class UnexpectedError(YtGrabError):
    """Anything else that went wrong inside the application or yt-dlp."""

    user_message = "Something unexpected went wrong. Details were saved to the log."
