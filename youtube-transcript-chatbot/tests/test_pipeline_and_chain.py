from dataclasses import replace
from types import SimpleNamespace

import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from yt_chatbot.chain import YouTubeChatbot, format_docs, format_history, get_llm
from yt_chatbot.config import Settings
from yt_chatbot.errors import ConfigError, InvalidVideoURL
from yt_chatbot.pipeline import load_video

VID = "dQw4w9WgXcQ"


class FakeTranscript:
    language_code, language, is_generated = "en", "English", False
    is_translatable, translation_languages = False, []

    def fetch(self):
        lines = [
            "Today we talk about photosynthesis in plants.",
            "Chlorophyll absorbs sunlight in the chloroplasts.",
            "[Music]",
            "Then we discuss the Calvin cycle and sugar production.",
            "Finally we cover cellular respiration in mitochondria.",
        ] * 12
        return [SimpleNamespace(text=t, start=float(i * 5), duration=5.0) for i, t in enumerate(lines)]


class CountingApi:
    def __init__(self):
        self.calls = 0

    def list(self, video_id):
        self.calls += 1
        return iter([FakeTranscript()])


@pytest.fixture
def settings(tmp_path):
    return Settings(chunk_size=200, chunk_overlap=40, top_k=3, cache_dir=tmp_path / "cache")


@pytest.fixture
def embeddings():
    return DeterministicFakeEmbedding(size=32)


def test_load_video_builds_index_and_caches(settings, embeddings):
    api = CountingApi()
    first = load_video(f"https://youtu.be/{VID}", settings, embeddings, api=api)
    assert not first.from_cache and first.meta.num_chunks > 1 and first.meta.video_id == VID
    assert api.calls == 1

    second = load_video(VID, settings, embeddings, api=api)
    assert second.from_cache and api.calls == 1  # served from disk, no new YouTube request
    assert second.meta == first.meta
    assert second.vectorstore.similarity_search("photosynthesis", k=1)

    third = load_video(VID, settings, embeddings, use_cache=False, api=api)
    assert not third.from_cache and api.calls == 2


def test_cache_invalidated_when_chunk_settings_change(settings, embeddings):
    api = CountingApi()
    load_video(VID, settings, embeddings, api=api)
    load_video(VID, replace(settings, chunk_size=300), embeddings, api=api)
    assert api.calls == 2


def test_load_video_invalid_url(settings, embeddings):
    with pytest.raises(InvalidVideoURL):
        load_video("garbage", settings, embeddings, api=CountingApi())


def test_rag_chain_end_to_end_with_followup(settings, embeddings):
    video = load_video(VID, settings, embeddings, api=CountingApi())
    llm = FakeListChatModel(responses=["Answer one.", "What does chlorophyll do?", "Answer two."])
    bot = YouTubeChatbot(video.vectorstore, llm, top_k=3)

    a1 = bot.ask("What is photosynthesis?")
    assert a1.text == "Answer one."
    assert a1.standalone_question == "What is photosynthesis?"  # no history -> no condense call
    assert 1 <= len(a1.sources) <= 3
    assert all(s.metadata["url"].startswith("https://www.youtube.com/") for s in a1.sources)

    a2 = bot.ask("What does it do?")  # follow-up -> condensed then answered
    assert a2.standalone_question == "What does chlorophyll do?"
    assert a2.text == "Answer two."
    assert len(bot.history) == 2

    bot.reset()
    assert bot.history == []


def test_ask_rejects_empty_question(settings, embeddings):
    video = load_video(VID, settings, embeddings, api=CountingApi())
    bot = YouTubeChatbot(video.vectorstore, FakeListChatModel(responses=["x"]))
    with pytest.raises(ValueError):
        bot.ask("   ")


def test_format_helpers():
    from langchain_core.documents import Document

    docs = [
        Document(page_content="later", metadata={"timestamp": "01:00", "start_seconds": 60}),
        Document(page_content="earlier", metadata={"timestamp": "00:05", "start_seconds": 5}),
    ]
    assert format_docs(docs) == "[00:05] earlier\n\n[01:00] later"
    assert format_history([]) == ""
    assert format_history([("q1", "a1"), ("q2", "a2")], max_turns=1) == "User: q2\nAssistant: a2"


def test_get_llm_requires_api_key():
    with pytest.raises(ConfigError):
        get_llm(Settings(fireworks_api_key=None))


def test_get_llm_builds_fireworks_model():
    llm = get_llm(Settings(fireworks_api_key="fw-test-key"))
    assert llm.model_name.endswith("llama-v3p1-8b-instruct")


def test_settings_validation():
    with pytest.raises(ConfigError):
        Settings(chunk_size=100, chunk_overlap=100)
    with pytest.raises(ConfigError):
        Settings(top_k=0)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "500")
    monkeypatch.setenv("CHUNK_OVERLAP", "50")
    monkeypatch.setenv("PREFERRED_LANGUAGES", "en, hi")
    s = Settings.from_env()
    assert (s.chunk_size, s.chunk_overlap, s.preferred_languages) == (500, 50, ("en", "hi"))
    monkeypatch.setenv("TOP_K", "abc")
    with pytest.raises(ConfigError):
        Settings.from_env()
