"""Unit tests for extract.py pure helpers."""
from __future__ import annotations

from yt_distill.pipeline import extract


def test_safe_title_normal():
    assert extract._safe_title("My Title") == "My_Title"


def test_safe_title_strips_punctuation():
    assert extract._safe_title("Title! With? Punctuation.") == "Title_With_Punctuation"


def test_safe_title_collapses_whitespace_and_dashes():
    assert extract._safe_title("a -- b   c") == "a_b_c"


def test_safe_title_empty_after_sanitization_returns_video():
    """Pathological all-punctuation input must fall back to the documented placeholder."""
    assert extract._safe_title("!!!") == "video"


def test_grade_transcript_known_sources():
    assert extract._grade_transcript("youtube-transcript-api") == "high"
    assert extract._grade_transcript("yt-dlp") == "high"
    assert extract._grade_transcript("pytube") == "medium"
    assert extract._grade_transcript("whisper") == "medium"


def test_grade_transcript_unknown_source_falls_back_to_low():
    assert extract._grade_transcript("nonexistent_source") == "low"


def test_format_clean_joins_with_space():
    entries = [(0.0, "Hello"), (1.0, "world")]
    assert extract._format_clean(entries) == "Hello world"
