"""Tests for the Whisper fallback wired into extract._do_transcript.

When tiers 1-3 all fail and Whisper credentials are present, _do_transcript
should download (or reuse) the cached video, extract audio, and re-invoke
fetch_transcript with allow_whisper=True and a real audio_path.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

import extract
from manifest import Manifest
from transcript import TranscriptResult


def _args(source: str, *, no_frames: bool = False, cookies_browser: str | None = None):
    return SimpleNamespace(
        source=source,
        no_frames=no_frames,
        cookies_from_browser=cookies_browser,
        force=False,
        force_ocr=False,
        max_frames=None,
        start=None,
        end=None,
        keep_video=False,
        out_dir=None,
    )


def _manifest(out_dir: Path, *, duration: float = 60.0) -> Manifest:
    return Manifest.load_or_create(
        out_dir,
        source_id="yt:abc",
        source_url="https://youtu.be/abc",
        title=out_dir.name,
        duration_seconds=duration,
    )


@patch("extract.fetch_transcript")
def test_no_fallback_when_tiers_succeed(mock_fetch, tmp_path):
    out_dir = tmp_path / "vid"
    out_dir.mkdir()
    mock_fetch.return_value = TranscriptResult(
        entries=[(0.0, "hello"), (1.0, "world")],
        source="youtube-transcript-api",
    )

    extract._do_transcript(_args("https://youtu.be/abc"), out_dir, _manifest(out_dir))

    assert mock_fetch.call_count == 1


@patch("extract._whisper_credentials_available", return_value=False)
@patch("extract.fetch_transcript")
def test_no_fallback_when_no_whisper_creds(mock_fetch, _creds, tmp_path):
    out_dir = tmp_path / "vid"
    out_dir.mkdir()
    mock_fetch.return_value = None

    extract._do_transcript(_args("https://youtu.be/abc"), out_dir, _manifest(out_dir))

    assert mock_fetch.call_count == 1


@patch("extract._whisper_credentials_available", return_value=True)
@patch("extract.fetch_transcript")
def test_no_fallback_when_no_frames_flag_set(mock_fetch, _creds, tmp_path):
    """If --no-frames was passed, we have no permission to download a video."""
    out_dir = tmp_path / "vid"
    out_dir.mkdir()
    mock_fetch.return_value = None

    extract._do_transcript(
        _args("https://youtu.be/abc", no_frames=True),
        out_dir,
        _manifest(out_dir),
    )

    assert mock_fetch.call_count == 1


@patch("extract._extract_audio_for_whisper")
@patch("extract._ensure_video_downloaded")
@patch("extract._whisper_credentials_available", return_value=True)
@patch("extract.fetch_transcript")
def test_falls_back_to_whisper_when_tiers_fail(
    mock_fetch, _creds, mock_ensure_video, mock_extract_audio, tmp_path
):
    out_dir = tmp_path / "vid"
    out_dir.mkdir()
    mock_ensure_video.return_value = "/tmp/fake_video.mp4"
    mock_extract_audio.return_value = "/tmp/fake_audio.m4a"
    mock_fetch.side_effect = [
        None,
        TranscriptResult(entries=[(0.0, "via whisper")], source="whisper"),
    ]

    extract._do_transcript(
        _args("https://youtu.be/abc", cookies_browser="chrome"),
        out_dir,
        _manifest(out_dir),
    )

    assert mock_fetch.call_count == 2, "fetch_transcript should be retried with whisper"
    second_call_kwargs = mock_fetch.call_args_list[1].kwargs
    assert second_call_kwargs.get("allow_whisper") is True
    assert second_call_kwargs.get("audio_path") == "/tmp/fake_audio.m4a"
    assert mock_ensure_video.called
    assert mock_extract_audio.called
