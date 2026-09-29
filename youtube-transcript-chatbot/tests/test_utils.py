import pytest

from yt_chatbot.errors import InvalidVideoURL
from yt_chatbot.utils import extract_video_id, format_timestamp, timestamp_url

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "value",
    [
        VID,
        f"https://www.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&t=42s&list=PL123",
        f"youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}?feature=share",
        f"  https://www.youtube.com/watch?v={VID}  ",
    ],
)
def test_extract_video_id_valid(value):
    assert extract_video_id(value) == VID


@pytest.mark.parametrize(
    "value",
    ["", "   ", "not a url", "https://example.com/watch?v=" + VID, "https://www.youtube.com/watch?v=short", "https://www.youtube.com/"],
)
def test_extract_video_id_invalid(value):
    with pytest.raises(InvalidVideoURL):
        extract_video_id(value)


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65.9) == "01:05"
    assert format_timestamp(3661) == "1:01:01"
    assert format_timestamp(-5) == "00:00"


def test_timestamp_url():
    assert timestamp_url(VID, 90.7) == f"https://www.youtube.com/watch?v={VID}&t=90s"
