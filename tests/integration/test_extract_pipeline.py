"""Integration tests for the extract.py pipeline.

These exercise the real transcript chain + manifest write against a local
public-domain test video (see tests/fixtures/test_video.mp4). The transcript
chain is expected to fail gracefully on a local mp4 (no captions / not a
YouTube ID), producing an "unavailable" placeholder, but the manifest must
still be created.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import extract


@pytest.mark.integration
def test_extract_local_video(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    assert src.exists(), "tests/fixtures/test_video.mp4 missing - see Task 6.2 Step 1"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))

    rc = extract.main([str(src), "--max-frames", "8", "--no-frames"])  # transcript-only first
    assert rc == 0

    # A single Generated_Data subdirectory should have been created (named after the title).
    out_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(out_dirs) == 1, f"expected 1 output dir, got {out_dirs}"
    od = out_dirs[0]

    manifest_path = od / "artifact_manifest.json"
    assert manifest_path.exists(), "artifact_manifest.json must be written"

    data = json.loads(manifest_path.read_text())
    assert data["schema_version"] == 1
    assert data["source_id"].startswith("local:")
    assert data["title"] == od.name
    # ffprobe-derived duration should match the trimmed clip (~30s)
    assert 25.0 <= float(data["duration_seconds"]) <= 35.0
    # extract section must exist (even if transcript was unavailable)
    assert data["extract"] is not None
    assert "transcript_source" in data["extract"]


@pytest.mark.integration
def test_extract_local_video_with_frames(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    rc = extract.main([str(src), "--max-frames", "8"])
    assert rc == 0
    out = next(tmp_path.iterdir())
    assert (out / "frames").is_dir()
    assert (out / "ocr.json").is_file()
    assert (out / "artifact_manifest.json").is_file()
