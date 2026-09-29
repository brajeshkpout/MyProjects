"""LangChain (LCEL) RAG pipeline built from modular runnables and parallel chains."""
from __future__ import annotations

from dataclasses import dataclass, field
from operator import itemgetter
from typing import Any, Sequence

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    Runnable,
    RunnableBranch,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.vectorstores import VectorStore

from .config import Settings
from .errors import ConfigError
from .prompts import CONDENSE_PROMPT, QA_PROMPT


# ----------------------------------------------------------------------------- LLM
def get_llm(settings: Settings) -> BaseChatModel:
    """Create the Fireworks-hosted LLaMA-3.1-8B-Instruct chat model."""
    if not settings.fireworks_api_key:
        raise ConfigError(
            "FIREWORKS_API_KEY is not set. Copy .env.example to .env and add your key "
            "(https://fireworks.ai/account/api-keys)."
        )
    from langchain_fireworks import ChatFireworks  # lazy import

    return ChatFireworks(
        model=settings.fireworks_model,
        api_key=settings.fireworks_api_key,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )


# ------------------------------------------------------------------ formatting helpers
def format_docs(docs: Sequence[Document]) -> str:
    """Render retrieved chunks, in video order, prefixed with their timestamps."""
    ordered = sorted(docs, key=lambda d: d.metadata.get("start_seconds", 0))
    return "\n\n".join(f"[{d.metadata.get('timestamp', '--:--')}] {d.page_content}" for d in ordered)


def format_history(history: Sequence[tuple[str, str]], max_turns: int = 4) -> str:
    """Render the last ``max_turns`` (question, answer) pairs as plain text."""
    recent = list(history)[-max_turns:]
    return "\n".join(f"User: {q}\nAssistant: {a}" for q, a in recent)


def _clean_question(text: str) -> str:
    return text.strip().strip('"').strip("'").strip()


# ------------------------------------------------------------------------- the chain
def build_rag_chain(retriever: Runnable, llm: BaseChatModel) -> Runnable:
    """Compose the full pipeline.

    Input : ``{"question": str, "chat_history": str}``
    Output: ``{"answer": str, "sources": list[Document], "standalone_question": str}``

    Steps
    -----
    1. *Condense* (conditional branch): turn follow-ups into standalone questions.
    2. *Retrieve* in a ``RunnableParallel`` together with the pass-through fields.
    3. *Format* the retrieved chunks into a context string.
    4. *Generate* with the custom QA prompt and the LLM.
    """
    parser = StrOutputParser()

    condense_chain = CONDENSE_PROMPT | llm | parser | RunnableLambda(_clean_question)
    standalone = RunnableBranch(
        (lambda x: bool(x["chat_history"].strip()), condense_chain),
        RunnableLambda(lambda x: x["question"]),
    )

    retrieve = RunnableParallel(
        docs=itemgetter("standalone_question") | retriever,
        question=itemgetter("question"),
        chat_history=itemgetter("chat_history"),
        standalone_question=itemgetter("standalone_question"),
    )

    return (
        RunnablePassthrough.assign(standalone_question=standalone)
        | retrieve
        | RunnablePassthrough.assign(context=RunnableLambda(lambda x: format_docs(x["docs"])))
        | RunnablePassthrough.assign(answer=QA_PROMPT | llm | parser)
        | RunnableLambda(
            lambda x: {
                "answer": x["answer"].strip(),
                "sources": x["docs"],
                "standalone_question": x["standalone_question"],
            }
        )
    )


def build_retriever(vectorstore: VectorStore, top_k: int = 4) -> Runnable:
    """MMR retrieval: relevant *and* diverse (chunks overlap, so plain top-k is redundant)."""
    return vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": top_k, "fetch_k": max(20, top_k * 5)},
    )


# ------------------------------------------------------------------------ chatbot API
@dataclass
class Answer:
    text: str
    sources: list[Document] = field(default_factory=list)
    standalone_question: str = ""


class YouTubeChatbot:
    """Stateful wrapper: keeps a short conversation history for follow-up questions."""

    def __init__(
        self,
        vectorstore: VectorStore,
        llm: BaseChatModel,
        top_k: int = 4,
        max_history_turns: int = 4,
    ) -> None:
        self.max_history_turns = max_history_turns
        self.history: list[tuple[str, str]] = []
        self.chain = build_rag_chain(build_retriever(vectorstore, top_k), llm)

    def ask(self, question: str) -> Answer:
        question = (question or "").strip()
        if not question:
            raise ValueError("Question must not be empty.")
        result: dict[str, Any] = self.chain.invoke(
            {
                "question": question,
                "chat_history": format_history(self.history, self.max_history_turns),
            }
        )
        self.history.append((question, result["answer"]))
        return Answer(
            text=result["answer"],
            sources=result["sources"],
            standalone_question=result["standalone_question"],
        )

    def reset(self) -> None:
        self.history.clear()
