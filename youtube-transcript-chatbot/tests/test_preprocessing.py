import pytest

from yt_chatbot.errors import EmptyTranscriptError
from yt_chatbot.preprocessing import TranscriptSegment, assemble_text, chunk_transcript, clean_text


def test_clean_text_removes_noise():
    assert clean_text("[Music] Hello&#39;s   world ♪") == "Hello's world"
    assert clean_text(">> Speaker says hi") == "Speaker says hi"
    assert clean_text("zero\u200bwidth") == "zerowidth"
    assert clean_text("[Applause]") == ""


def test_clean_text_preserves_multilingual_text():
    hindi = "नमस्ते दोस्तों, आज हम सीखेंगे।"
    japanese = "こんにちは、世界。"
    assert clean_text(hindi) == hindi
    assert clean_text(japanese) == japanese


def test_assemble_text_offsets_map_back_to_segments():
    segs = [
        TranscriptSegment("first line", 0.0),
        TranscriptSegment("[Music]", 3.0),
        TranscriptSegment("second line", 5.0),
        TranscriptSegment("third", 9.5),
    ]
    text, offsets = assemble_text(segs)
    assert text == "first line second line third"
    assert offsets == [(0, 0.0), (11, 5.0), (23, 9.5)]
    for pos, _ in offsets:
        assert text[pos] != " "


def test_chunk_transcript_metadata_and_timestamps():
    segs = [TranscriptSegment(f"This is sentence number {i} of the talk.", float(i * 10)) for i in range(60)]
    docs = chunk_transcript(segs, video_id="dQw4w9WgXcQ", chunk_size=200, chunk_overlap=40, language="en")
    assert len(docs) > 3
    starts = [d.metadata["start_seconds"] for d in docs]
    assert starts == sorted(starts)  # chunks progress through the video
    assert docs[0].metadata["start_seconds"] == 0.0
    assert docs[-1].metadata["start_seconds"] > 300
    for i, d in enumerate(docs):
        assert len(d.page_content) <= 200
        assert d.metadata["chunk_id"] == i
        assert d.metadata["video_id"] == "dQw4w9WgXcQ"
        assert d.metadata["language"] == "en"
        assert d.metadata["url"].startswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=")


def test_chunk_timestamp_points_to_segment_containing_chunk_start():
    segs = [TranscriptSegment(f"unique{i:03d} " + "word " * 10, float(i)) for i in range(40)]
    docs = chunk_transcript(segs, video_id="dQw4w9WgXcQ", chunk_size=150, chunk_overlap=20)
    for d in docs:
        first_token = d.page_content.split()[0]
        if first_token.startswith("unique"):
            assert d.metadata["start_seconds"] == float(int(first_token[len("unique"):]))


def test_chunk_transcript_handles_cjk_without_spaces():
    segs = [TranscriptSegment("これはテストです。" * 5, float(i)) for i in range(20)]
    docs = chunk_transcript(segs, video_id="dQw4w9WgXcQ", chunk_size=60, chunk_overlap=10)
    assert len(docs) > 1
    assert all(len(d.page_content) <= 60 for d in docs)


def test_chunk_transcript_empty_raises():
    with pytest.raises(EmptyTranscriptError):
        chunk_transcript([TranscriptSegment("[Music]", 0.0)], video_id="dQw4w9WgXcQ")
