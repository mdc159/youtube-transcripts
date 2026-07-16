"""Unit tests for transcript._extract_video_id helper.

Regression coverage for the bug where the full URL was passed straight to
youtube-transcript-api, which then concatenated it onto its own URL template.
"""
from yt_distill.stages.transcript import _extract_video_id


def test_extracts_id_from_youtu_be_short_url():
    assert _extract_video_id("https://youtu.be/abc123XYZ_-") == "abc123XYZ_-"


def test_extracts_id_from_youtu_be_with_query():
    assert _extract_video_id("https://youtu.be/abc123XYZ_-?t=10") == "abc123XYZ_-"


def test_extracts_id_from_watch_url():
    assert _extract_video_id("https://www.youtube.com/watch?v=abc123XYZ_-&t=10") == "abc123XYZ_-"


def test_extracts_id_from_watch_url_no_www():
    assert _extract_video_id("https://youtube.com/watch?v=abc123XYZ_-") == "abc123XYZ_-"


def test_extracts_id_from_embed_url():
    assert _extract_video_id("https://www.youtube.com/embed/abc123XYZ_-") == "abc123XYZ_-"


def test_passes_through_bare_id():
    assert _extract_video_id("abc123XYZ_-") == "abc123XYZ_-"


def test_returns_none_for_non_youtube_url():
    assert _extract_video_id("https://example.com/video.mp4") is None


def test_returns_none_for_local_path():
    assert _extract_video_id("/home/user/video.mp4") is None


def test_returns_none_for_arbitrary_string():
    assert _extract_video_id("not a url at all") is None
