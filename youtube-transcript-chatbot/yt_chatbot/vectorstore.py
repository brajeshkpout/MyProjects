"""Embeddings (Hugging Face MiniLM-L6-v2) and FAISS vector store helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


@lru_cache(maxsize=2)
def get_embeddings(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> Embeddings:
    """Load the sentence-transformers embedding model (downloaded on first use)."""
    from langchain_huggingface import HuggingFaceEmbeddings  # lazy: heavy import

    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def build_vectorstore(docs: Sequence[Document], embeddings: Embeddings) -> FAISS:
    """Embed ``docs`` and index them in an in-memory FAISS store."""
    if not docs:
        raise ValueError("Cannot build a vector store from zero documents.")
    return FAISS.from_documents(list(docs), embeddings)


def save_vectorstore(store: FAISS, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    store.save_local(str(path))


def load_vectorstore(path: Path, embeddings: Embeddings) -> FAISS:
    """Load an index previously written by :func:`save_vectorstore`.

    ``allow_dangerous_deserialization`` is required by LangChain because FAISS
    metadata is pickled. It is safe here because we only ever load indexes that
    this application wrote itself into its own cache directory.
    """
    return FAISS.load_local(str(path), embeddings, allow_dangerous_deserialization=True)
