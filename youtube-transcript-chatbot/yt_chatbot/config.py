"""Central configuration, loaded from environment variables / a ``.env`` file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/llama-v3p1-8b-instruct"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _get_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Every field can be overridden through an env variable."""

    fireworks_api_key: str | None = None
    fireworks_model: str = DEFAULT_FIREWORKS_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 4
    temperature: float = 0.2
    max_tokens: int = 512
    # Transcript languages accepted as-is (no translation needed).
    preferred_languages: tuple[str, ...] = ("en",)
    # Language every other transcript is translated into ("" disables translation).
    target_language: str = "en"
    cache_dir: Path = Path(".cache/indexes")

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ConfigError("CHUNK_SIZE must be greater than 0")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ConfigError("CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE")
        if self.top_k <= 0:
            raise ConfigError("TOP_K must be greater than 0")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            fireworks_api_key=os.getenv("FIREWORKS_API_KEY") or None,
            fireworks_model=os.getenv("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            embedding_model=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            chunk_size=_get_int("CHUNK_SIZE", 800),
            chunk_overlap=_get_int("CHUNK_OVERLAP", 150),
            top_k=_get_int("TOP_K", 4),
            temperature=_get_float("TEMPERATURE", 0.2),
            max_tokens=_get_int("MAX_TOKENS", 512),
            preferred_languages=_get_list("PREFERRED_LANGUAGES", ("en",)),
            target_language=os.getenv("TARGET_LANGUAGE", "en").strip(),
            cache_dir=Path(os.getenv("CACHE_DIR", ".cache/indexes")),
        )
