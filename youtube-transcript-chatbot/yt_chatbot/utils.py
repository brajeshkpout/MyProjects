"""Small helpers: video-id parsing and timestamp formatting."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .errors import InvalidVideoURL

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
}
_PATH_PREFIXES = {"embed", "shorts", "live", "v"}


def extract_video_id(url_or_id: str) -> str:
    """Return the 11-character YouTube video id from a URL (or a bare id).

    Supports watch, youtu.be, embed, shorts, live and music.youtube.com links.
    Raises :class:`InvalidVideoURL` when no valid id can be found.
    """
    if not isinstance(url_or_id, str) or not url_or_id.strip():
        raise InvalidVideoURL("Please provide a YouTube URL or video id.")

    value = url_or_id.strip()
    if _VIDEO_ID_RE.match(value):
        return value

    if not _SCHEME_RE.match(value):
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    candidate: str | None = None
    segments = [seg for seg in parsed.path.split("/") if seg]

    if host == "youtu.be":
        candidate = segments[0] if segments else None
    elif host in _YOUTUBE_HOSTS:
        if segments and segments[0] == "watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            candidate = segments[1]

    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    raise InvalidVideoURL(f"Could not find a valid YouTube video id in: {url_or_id!r}")


def format_timestamp(seconds: float) -> str:
    """Format seconds as ``mm:ss`` or ``h:mm:ss``."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def timestamp_url(video_id: str, seconds: float) -> str:
    """Deep link that opens the video at the given second."""
    return f"https://www.youtube.com/watch?v={video_id}&t={max(0, int(seconds))}s"
