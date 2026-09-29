"""Custom exceptions so callers (CLI / UI) can show friendly messages."""


class YtChatbotError(Exception):
    """Base class for all expected, user-facing errors."""


class InvalidVideoURL(YtChatbotError, ValueError):
    """The supplied string is not a valid YouTube URL or video id."""


class TranscriptError(YtChatbotError):
    """A transcript could not be retrieved for the video."""


class EmptyTranscriptError(YtChatbotError):
    """The transcript exists but contains no usable text after cleaning."""


class ConfigError(YtChatbotError):
    """Required configuration (e.g. the Fireworks API key) is missing or invalid."""
