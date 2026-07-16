from pathlib import Path
import json
import time
from yt_distill import clean


def _setup(root: Path, age_days: int = 0):
    od = root / "Generated_Data" / "T"
    (od / "frames").mkdir(parents=True)
    (od / "frames" / "f1.jpg").write_bytes(b"x")
    (od / "ocr.json").write_text("{}")
    (root / "media_cache" / "T").mkdir(parents=True)
    (root / "media_cache" / "T" / "video.mp4").write_bytes(b"v")
    (od / "artifact_manifest.json").write_text(json.dumps({"extract": {"completed_at": "2020-01-01T00:00:00Z"}}))
    return od


def test_dry_run_does_not_delete(tmp_path):
    od = _setup(tmp_path)
    rc = clean.main(["--delete-video", "--delete-frames", "--root", str(tmp_path)])
    assert rc == 0
    assert (od / "frames" / "f1.jpg").exists()  # still there
    assert (tmp_path / "media_cache" / "T" / "video.mp4").exists()


def test_apply_deletes(tmp_path):
    od = _setup(tmp_path)
    rc = clean.main(["--delete-video", "--delete-frames", "--apply", "--root", str(tmp_path)])
    assert rc == 0
    assert not (od / "frames" / "f1.jpg").exists()
    assert not (tmp_path / "media_cache" / "T" / "video.mp4").exists()
    assert (od / "ocr.json").exists()  # OCR retained
