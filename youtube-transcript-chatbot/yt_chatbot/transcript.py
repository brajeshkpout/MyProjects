"""Transcript extraction with multilingual handling (via youtube-transcript-api >= 1.0)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    IpBlocked,
    NotTranslatable,
    RequestBlocked,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

from .errors import TranscriptError
from .preprocessing import TranscriptSegment


@dataclass(frozen=True)
class TranscriptResult:
    """A fetched transcript plus information on how it was obtained."""

    video_id: str
    language: str
    language_code: str
    is_generated: bool
    translated: bool
    segments: list[TranscriptSegment]


def _same_language(code: str, wanted: str) -> bool:
    """``en-GB`` matches ``en``; ``zh-Hans`` matches only ``zh-Hans`` / ``zh``."""
    code, wanted = code.lower(), wanted.lower()
    return code == wanted or code.split("-")[0] == wanted.split("-")[0]


def _pick_native(transcripts: list[Any], preferred: Iterable[str]) -> Any | None:
    """First transcript in a preferred language (manual captions beat auto-generated)."""
    for lang in preferred:
        matches = [t for t in transcripts if _same_language(t.language_code, lang)]
        if matches:
            return sorted(matches, key=lambda t: t.is_generated)[0]
    return None


def _can_translate_to(transcript: Any, target: str) -> bool:
    if not getattr(transcript, "is_translatable", False):
        return False
    return any(
        lang.language_code.lower() == target.lower()
        for lang in (getattr(transcript, "translation_languages", None) or [])
    )


def _to_segments(fetched: Iterable[Any]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(text=s.text, start=float(s.start), duration=float(s.duration))
        for s in fetched
    ]


def fetch_transcript(
    video_id: str,
    preferred_languages: Iterable[str] = ("en",),
    target_language: str = "en",
    api: Any | None = None,
) -> TranscriptResult:
    """Fetch the best available transcript for ``video_id``.

    Strategy (multilingual pre-processing):

    1. Use a transcript in one of ``preferred_languages`` if it exists
       (manually created captions are preferred over auto-generated ones).
    2. Otherwise take the best available transcript (manual first) and, if
       YouTube can translate it, translate it into ``target_language`` so it
       matches the English-only embedding model.
    3. If it cannot be translated, use it as-is.
    """
    api = api or YouTubeTranscriptApi()
    preferred = tuple(preferred_languages)

    try:
        transcripts = list(api.list(video_id))
    except TranscriptsDisabled as exc:
        raise TranscriptError("Subtitles are disabled for this video.") from exc
    except AgeRestricted as exc:
        raise TranscriptError("This video is age-restricted and its transcript is not accessible.") from exc
    except (VideoUnavailable, VideoUnplayable, InvalidVideoId) as exc:
        raise TranscriptError("This video is unavailable, private or the id is invalid.") from exc
    except (IpBlocked, RequestBlocked) as exc:
        raise TranscriptError(
            "YouTube blocked the request (common on cloud/VPN IPs). "
            "Run the app from a home network or configure a proxy for youtube-transcript-api."
        ) from exc
    except CouldNotRetrieveTranscript as exc:
        raise TranscriptError(f"Could not retrieve the transcript: {exc}") from exc

    if not transcripts:
        raise TranscriptError("No transcripts are available for this video.")

    try:
        chosen = _pick_native(transcripts, preferred)
        translated = False
        if chosen is None:
            chosen = sorted(transcripts, key=lambda t: t.is_generated)[0]
            if target_language and _can_translate_to(chosen, target_language):
                try:
                    chosen = chosen.translate(target_language)
                    translated = True
                except (NotTranslatable, TranslationLanguageNotAvailable):
                    pass  # fall back to the untranslated transcript
        fetched = chosen.fetch()
    except CouldNotRetrieveTranscript as exc:
        raise TranscriptError(f"Could not retrieve the transcript: {exc}") from exc

    segments = _to_segments(fetched)
    if not segments:
        raise TranscriptError("The transcript is empty.")

    return TranscriptResult(
        video_id=video_id,
        language=chosen.language,
        language_code=chosen.language_code,
        is_generated=bool(chosen.is_generated),
        translated=translated,
        segments=segments,
    )
