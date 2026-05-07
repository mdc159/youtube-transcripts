# tests/test_manifest.py
import pytest
from manifest import derive_source_id


def test_youtube_url_to_source_id():
    assert derive_source_id("https://www.youtube.com/watch?v=KE39P4qBjDk") == "yt:KE39P4qBjDk"
    assert derive_source_id("https://youtu.be/KE39P4qBjDk") == "yt:KE39P4qBjDk"
    assert derive_source_id("KE39P4qBjDk") == "yt:KE39P4qBjDk"


def test_local_path_to_source_id():
    sid = derive_source_id("/abs/path/to/video.mp4")
    assert sid.startswith("local:")
    assert len(sid) == len("local:") + 12  # 12-char sha1 prefix


def test_clip_range_appends_suffix():
    base = derive_source_id("KE39P4qBjDk")
    clipped = derive_source_id("KE39P4qBjDk", start=15, end=45)
    assert clipped == base + "#15-45"


def test_other_url_uses_sha1():
    sid = derive_source_id("https://example.com/some/path?x=1")
    assert sid.startswith("web:")
    assert len(sid) == len("web:") + 12
