from unittest.mock import patch
import pytest
from transcript import fetch_transcript, TranscriptResult


def _entries():
    return [(0.0, "hello"), (1.5, "world")]


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_first_method_wins(api, pyt, ytdlp, whisp):
    api.return_value = _entries()
    res = fetch_transcript("vid")
    assert res.entries == _entries()
    assert res.source == "youtube-transcript-api"
    assert pyt.call_count == 0
    assert ytdlp.call_count == 0
    assert whisp.call_count == 0


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_falls_through_to_whisper(api, pyt, ytdlp, whisp):
    api.side_effect = Exception("no captions")
    pyt.side_effect = Exception("no captions")
    ytdlp.side_effect = Exception("no captions")
    whisp.return_value = _entries()
    res = fetch_transcript("vid", allow_whisper=True, audio_path="/tmp/audio.mp3")
    assert res.source == "whisper"
    assert res.entries == _entries()


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_all_fail_returns_none(api, pyt, ytdlp, whisp):
    api.side_effect = Exception("x")
    pyt.side_effect = Exception("x")
    ytdlp.side_effect = Exception("x")
    whisp.side_effect = Exception("x")
    res = fetch_transcript("vid", allow_whisper=True, audio_path="/tmp/x.mp3")
    assert res is None
