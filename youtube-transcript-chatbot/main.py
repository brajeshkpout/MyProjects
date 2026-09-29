"""Command-line interface for the YouTube Transcript Chatbot.

Examples
--------
    python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python main.py VIDEO_ID -q "What is the main topic?" --sources
"""
from __future__ import annotations

import argparse
import dataclasses
import sys

from yt_chatbot.chain import Answer, YouTubeChatbot, get_llm
from yt_chatbot.config import Settings
from yt_chatbot.errors import YtChatbotError
from yt_chatbot.pipeline import load_video

EXIT_WORDS = {"exit", "quit", "q", ":q"}


def _print_answer(answer: Answer, show_sources: bool) -> None:
    print(f"\nBot: {answer.text}\n")
    if show_sources:
        print("Sources:")
        for doc in answer.sources:
            print(f"  [{doc.metadata.get('timestamp')}] {doc.metadata.get('url')}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chat with any YouTube video using its transcript (RAG).")
    parser.add_argument("video", help="YouTube URL or 11-character video id")
    parser.add_argument("-q", "--question", help="Ask a single question and exit")
    parser.add_argument("-k", "--top-k", type=int, help="Number of transcript chunks to retrieve")
    parser.add_argument("--sources", action="store_true", help="Print timestamped source links")
    parser.add_argument("--no-cache", action="store_true", help="Ignore and do not write the on-disk index cache")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.top_k:
        settings = dataclasses.replace(settings, top_k=args.top_k)

    try:
        llm = get_llm(settings)  # fail fast if the API key is missing
        print("Fetching transcript and building the index (first run downloads the embedding model)...")
        video = load_video(args.video, settings, use_cache=not args.no_cache)
        bot = YouTubeChatbot(video.vectorstore, llm, top_k=settings.top_k)
    except YtChatbotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    meta = video.meta
    note = " (translated)" if meta.translated else ""
    print(f"Ready: {meta.num_chunks} chunks | transcript language: {meta.language}{note}"
          f"{' | loaded from cache' if video.from_cache else ''}")

    try:
        if args.question:
            _print_answer(bot.ask(args.question), args.sources)
            return 0

        print("Ask questions about the video. Type 'exit' to quit.\n")
        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not question:
                continue
            if question.lower() in EXIT_WORDS:
                return 0
            _print_answer(bot.ask(question), args.sources)
    except YtChatbotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # network / LLM errors
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
