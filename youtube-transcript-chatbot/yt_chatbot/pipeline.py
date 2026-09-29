"""End-to-end ingestion: URL -> transcript -> chunks -> embeddings -> FAISS (with disk cache)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings

from .config import Settings
from .preprocessing import chunk_transcript
from .transcript import fetch_transcript
from .utils import extract_video_id
from .vectorstore import build_vectorstore, get_embeddings, load_vectorstore, save_vectorstore

META_FILE = "meta.json"


@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    language: str
    language_code: str
    is_generated: bool
    translated: bool
    num_chunks: int


@dataclass(frozen=True)
class VideoIndex:
    meta: VideoMeta
    vectorstore: FAISS
    from_cache: bool = False


def _cache_path(video_id: str, settings: Settings) -> Path:
    fingerprint = "|".join(
        [
            settings.embedding_model,
            str(settings.chunk_size),
            str(settings.chunk_overlap),
            settings.target_language,
            ",".join(settings.preferred_languages),
        ]
    )
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:10]
    return Path(settings.cache_dir) / f"{video_id}-{digest}"


def load_video(
    url_or_id: str,
    settings: Settings,
    embeddings: Embeddings | None = None,
    use_cache: bool = True,
    api: Any | None = None,
) -> VideoIndex:
    """Build (or load from cache) the searchable index for a YouTube video."""
    video_id = extract_video_id(url_or_id)
    embeddings = embeddings or get_embeddings(settings.embedding_model)
    path = _cache_path(video_id, settings)

    if use_cache and (path / META_FILE).is_file() and (path / "index.faiss").is_file():
        try:
            meta = VideoMeta(**json.loads((path / META_FILE).read_text(encoding="utf-8")))
            return VideoIndex(meta, load_vectorstore(path, embeddings), from_cache=True)
        except Exception:
            pass  # corrupt / incompatible cache: rebuild below

    result = fetch_transcript(
        video_id,
        preferred_languages=settings.preferred_languages,
        target_language=settings.target_language,
        api=api,
    )
    docs = chunk_transcript(
        result.segments,
        video_id=video_id,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        language=result.language_code,
    )
    store = build_vectorstore(docs, embeddings)
    meta = VideoMeta(
        video_id=video_id,
        language=result.language,
        language_code=result.language_code,
        is_generated=result.is_generated,
        translated=result.translated,
        num_chunks=len(docs),
    )

    if use_cache:
        try:
            save_vectorstore(store, path)
            (path / META_FILE).write_text(json.dumps(asdict(meta)), encoding="utf-8")
        except OSError:
            pass  # caching is best-effort
    return VideoIndex(meta, store, from_cache=False)
