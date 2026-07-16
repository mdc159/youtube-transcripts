# tests/test_manifest.py
import json
import pytest
from yt_distill.core.manifest import derive_source_id, Manifest, MANIFEST_FILENAME


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


def test_manifest_init_defaults(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="https://x", title="T", duration_seconds=10.0)
    assert m.data["schema_version"] == 1
    assert m.data["source_id"] == "yt:abc"
    assert m.data["distill_runs"] == []
    assert m.data["extract"] is None


def test_manifest_persistence(tmp_path):
    m1 = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    m1.set_extract({"transcript_source": "captions", "transcript_quality": "high", "frame_budget_used": 30, "files": {}})
    m1.save()

    m2 = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    assert m2.data["extract"]["transcript_source"] == "captions"


def test_manifest_add_distill_run(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    m.add_distill_run({"style": "coding_agent", "model_profile": "gemini-3-flash", "prompt_contract_version": 1, "files": {}, "token_usage": {}})
    m.save()
    raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert len(raw["distill_runs"]) == 1
    assert raw["distill_runs"][0]["style"] == "coding_agent"


def test_manifest_corruption_detection_for_file(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    transcript = tmp_path / "transcript.txt"
    transcript.write_bytes(b"hello")
    m.record_file("extract", "formatted_transcript", transcript)
    m.save()
    transcript.write_bytes(b"changed")  # corrupt
    assert m.file_intact("extract", "formatted_transcript") is False


def test_manifest_intact_for_directory(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "f1.jpg").write_bytes(b"a")
    (frames_dir / "f2.jpg").write_bytes(b"b")
    m.record_file("extract", "frames_dir", frames_dir)
    m.save()
    assert m.file_intact("extract", "frames_dir") is True
    (frames_dir / "f3.jpg").write_bytes(b"c")  # frame count drift
    assert m.file_intact("extract", "frames_dir") is False
