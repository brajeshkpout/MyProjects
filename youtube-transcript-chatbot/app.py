"""Streamlit web UI:  streamlit run app.py"""
from __future__ import annotations

import dataclasses

import streamlit as st

from yt_chatbot.chain import YouTubeChatbot, get_llm
from yt_chatbot.config import Settings
from yt_chatbot.errors import YtChatbotError
from yt_chatbot.pipeline import load_video
from yt_chatbot.utils import extract_video_id
from yt_chatbot.vectorstore import get_embeddings

st.set_page_config(page_title="YouTube Transcript Chatbot", page_icon="🎬", layout="wide")


@st.cache_resource(show_spinner="Loading embedding model (first run downloads it)...")
def cached_embeddings(model_name: str):
    return get_embeddings(model_name)


def init_state() -> None:
    st.session_state.setdefault("bot", None)
    st.session_state.setdefault("video", None)
    st.session_state.setdefault("messages", [])


def render_sources(sources: list[dict]) -> None:
    with st.expander("Sources (transcript excerpts)"):
        for src in sources:
            st.markdown(f"**[{src['timestamp']}]({src['url']})**  \n{src['text']}")


init_state()
settings = Settings.from_env()

st.title("🎬 YouTube Transcript Chatbot")
st.caption("Retrieval-Augmented Generation over video transcripts: FAISS + MiniLM embeddings + LLaMA-3.1-8B (Fireworks)")

with st.sidebar:
    st.header("Setup")
    api_key = st.text_input(
        "Fireworks API key",
        type="password",
        value=settings.fireworks_api_key or "",
        help="Or set FIREWORKS_API_KEY in your .env file.",
    )
    url = st.text_input("YouTube URL or video id", placeholder="https://www.youtube.com/watch?v=...")
    load_clicked = st.button("Load video", type="primary", use_container_width=True)
    if st.button("Clear chat", use_container_width=True) and st.session_state.bot is not None:
        st.session_state.bot.reset()
        st.session_state.messages = []
        st.rerun()

if load_clicked:
    run_settings = dataclasses.replace(settings, fireworks_api_key=api_key.strip() or None)
    try:
        llm = get_llm(run_settings)
        embeddings = cached_embeddings(run_settings.embedding_model)
        with st.spinner("Fetching transcript and building the index..."):
            video = load_video(url, run_settings, embeddings=embeddings)
        st.session_state.video = video
        st.session_state.bot = YouTubeChatbot(video.vectorstore, llm, top_k=run_settings.top_k)
        st.session_state.messages = []
    except YtChatbotError as exc:
        st.error(str(exc))
    except Exception as exc:  # network / model download errors
        st.error(f"Unexpected error: {exc}")

video = st.session_state.video
bot = st.session_state.bot

if video is None or bot is None:
    st.info("Enter your Fireworks API key and a YouTube link in the sidebar, then click **Load video**.")
    st.stop()

meta = video.meta
left, right = st.columns([1, 2])
with left:
    st.video(f"https://www.youtube.com/watch?v={meta.video_id}")
    kind = "auto-generated" if meta.is_generated else "manual"
    note = " -> translated" if meta.translated else ""
    st.caption(f"Transcript: {meta.language} ({kind}{note}) | {meta.num_chunks} chunks"
               f"{' | cached' if video.from_cache else ''}")

with right:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                render_sources(msg["sources"])

    question = st.chat_input("Ask something about the video...")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Thinking..."):
                    answer = bot.ask(question)
                sources = [
                    {"timestamp": d.metadata.get("timestamp"), "url": d.metadata.get("url"), "text": d.page_content}
                    for d in sorted(answer.sources, key=lambda d: d.metadata.get("start_seconds", 0))
                ]
                st.markdown(answer.text)
                render_sources(sources)
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer.text, "sources": sources}
                )
            except Exception as exc:
                st.error(f"Could not get an answer: {exc}")
