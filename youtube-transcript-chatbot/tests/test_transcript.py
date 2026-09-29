from types import SimpleNamespace

import pytest
from youtube_transcript_api import IpBlocked, TranscriptsDisabled, VideoUnavailable

from yt_chatbot.errors import TranscriptError
from yt_chatbot.transcript import fetch_transcript


class FakeTranscript:
    def __init__(self, code, language, generated=False, translatable=True, targets=("en", "hi")):
        self.language_code = code
        self.language = language
        self.is_generated = generated
        self.is_translatable = translatable
        self.translation_languages = [SimpleNamespace(language=t, language_code=t) for t in targets]
        self.translated_to = None

    def fetch(self):
        tag = self.translated_to or self.language_code
        return [SimpleNamespace(text=f"line in {tag}", start=1.0, duration=2.0)]

    def translate(self, code):
        clone = FakeTranscript(code, f"translated-{code}", generated=self.is_generated)
        clone.translated_to = code
        return clone


class FakeApi:
    def __init__(self, transcripts=None, error=None):
        self._transcripts, self._error = transcripts or [], error

    def list(self, video_id):
        if self._error:
            raise self._error
        return iter(self._transcripts)


def test_prefers_manual_native_language_over_generated():
    api = FakeApi([FakeTranscript("en", "English", generated=True), FakeTranscript("en-GB", "English (UK)", generated=False)])
    res = fetch_transcript("vid", ("en",), "en", api=api)
    assert res.language_code == "en-GB" and not res.translated and not res.is_generated


def test_translates_foreign_transcript_to_target():
    api = FakeApi([FakeTranscript("hi", "Hindi", generated=True)])
    res = fetch_transcript("vid", ("en",), "en", api=api)
    assert res.translated and res.language_code == "en"
    assert res.segments[0].text == "line in en"


def test_falls_back_to_original_when_not_translatable():
    api = FakeApi([FakeTranscript("ja", "Japanese", translatable=False)])
    res = fetch_transcript("vid", ("en",), "en", api=api)
    assert not res.translated and res.language_code == "ja"


def test_translation_disabled_when_target_empty():
    api = FakeApi([FakeTranscript("hi", "Hindi")])
    res = fetch_transcript("vid", ("en",), "", api=api)
    assert not res.translated and res.language_code == "hi"


def test_prefers_manual_foreign_over_generated_foreign():
    api = FakeApi([FakeTranscript("hi", "Hindi", generated=True), FakeTranscript("fr", "French", generated=False)])
    res = fetch_transcript("vid", ("en",), "", api=api)
    assert res.language_code == "fr"


@pytest.mark.parametrize("exc", [TranscriptsDisabled("vid"), VideoUnavailable("vid"), IpBlocked("vid")])
def test_youtube_errors_become_transcript_error(exc):
    with pytest.raises(TranscriptError):
        fetch_transcript("vid", api=FakeApi(error=exc))


def test_no_transcripts_raises():
    with pytest.raises(TranscriptError):
        fetch_transcript("vid", api=FakeApi([]))
