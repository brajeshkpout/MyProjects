"""Transcript cleaning and recursive chunking (with timestamp tracking)."""
from __future__ import annotations

import html
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .errors import EmptyTranscriptError
from .utils import format_timestamp, timestamp_url

# Sentence boundaries for Latin, Devanagari (danda) and CJK text, then words.
SEPARATORS = ["\n\n", "\n", "。", "！", "？", "। ", "? ", "! ", ". ", "; ", ", ", " ", ""]

_SOUND_TAG_RE = re.compile(r"\[[^\]\n]{1,40}\]")  # [Music], [Applause], [संगीत] ...
_SPEAKER_RE = re.compile(r"^\s*>>+\s*")
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TranscriptSegment:
    """One caption line as returned by YouTube."""

    text: str
    start: float
    duration: float = 0.0


def clean_text(text: str) -> str:
    """Language-agnostic normalisation of a single caption line.

    * decodes HTML entities (``&amp;#39;`` -> ``'``)
    * applies Unicode NFC normalisation (safe for Indic / Arabic / CJK scripts)
    * strips sound tags like ``[Music]``, music notes, speaker markers and
      zero-width characters
    * collapses all whitespace
    """
    text = html.unescape(text or "")
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _SOUND_TAG_RE.sub(" ", text)
    text = _SPEAKER_RE.sub("", text)
    text = text.replace("♪", " ").replace("♫", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def assemble_text(segments: list[TranscriptSegment]) -> tuple[str, list[tuple[int, float]]]:
    """Join cleaned segments into one string.

    Returns ``(text, offsets)`` where ``offsets`` is a sorted list of
    ``(char_position, start_seconds)`` so a character index can later be mapped
    back to a position in the video.
    """
    parts: list[str] = []
    offsets: list[tuple[int, float]] = []
    pos = 0
    for seg in segments:
        cleaned = clean_text(seg.text)
        if not cleaned:
            continue
        if parts:
            pos += 1  # the joining space
        offsets.append((pos, float(seg.start)))
        parts.append(cleaned)
        pos += len(cleaned)
    return " ".join(parts), offsets


def chunk_transcript(
    segments: list[TranscriptSegment],
    video_id: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    language: str | None = None,
) -> list[Document]:
    """Clean, join and split a transcript into overlapping chunks.

    Each returned :class:`Document` carries ``video_id``, ``chunk_id``,
    ``start_seconds``, ``timestamp``, ``url`` and ``language`` metadata.
    """
    text, offsets = assemble_text(segments)
    if not text:
        raise EmptyTranscriptError("The transcript contains no usable text.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        keep_separator="end",
        add_start_index=True,
    )
    docs = splitter.create_documents([text])

    positions = [pos for pos, _ in offsets]
    for chunk_id, doc in enumerate(docs):
        start_index = doc.metadata.get("start_index", 0)
        if not isinstance(start_index, int) or start_index < 0:
            start_index = 0
        seg_idx = max(0, bisect_right(positions, start_index) - 1)
        start_seconds = offsets[seg_idx][1]
        doc.metadata.update(
            {
                "video_id": video_id,
                "chunk_id": chunk_id,
                "start_seconds": start_seconds,
                "timestamp": format_timestamp(start_seconds),
                "url": timestamp_url(video_id, start_seconds),
                "language": language,
            }
        )
    return docs
