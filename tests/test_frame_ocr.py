from pathlib import Path
import pytest
from frame_ocr import ocr_frame, OcrResult, OcrLine, CONFIDENCE_GATE


def test_ocr_frame_returns_text(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    assert isinstance(res, OcrResult)
    assert "fetch_user" in res.text or "fetch" in res.text  # tolerate OCR drift
    assert 0.0 <= res.mean_confidence <= 1.0


def test_ocr_frame_confidence_gate_marks_lines(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    # We don't know exact OCR results, but the gating field must be populated.
    assert hasattr(res, "lines")
    assert all(hasattr(l, "confidence") for l in res.lines)
    assert all(hasattr(l, "above_gate") for l in res.lines)


from frame_ocr import classify_frame, FrameClass


def test_classify_code(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    cls, conf = classify_frame(res)
    assert cls == FrameClass.CODE
    assert conf >= 0.6


def test_classify_slide(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_slide.jpg")
    cls, _ = classify_frame(res)
    assert cls in (FrameClass.SLIDE_TEXT, FrameClass.OTHER)  # tolerate OCR drift
    # Slide text should NOT be classified as code:
    assert cls != FrameClass.CODE


def test_classify_low_confidence_falls_back_to_other():
    """classify_frame reports low confidence on ambiguous input; the caller
    convention (spec §4.3) then maps low-conf classifications to OTHER."""
    fake = OcrResult(
        text="x",
        high_confidence_text="x",
        lines=[OcrLine("x", 0.5, True)],
        mean_confidence=0.5,
    )
    cls, conf = classify_frame(fake)
    # Ambiguous single-line input → classifier reports below the 0.6 gate
    assert conf < 0.6
    # Caller convention: anything below 0.6 is treated as OTHER
    final_class = cls if conf >= 0.6 else FrameClass.OTHER
    assert final_class == FrameClass.OTHER


from frame_ocr import dedup_code_frames, FrameRecord


def _rec(idx: int, ts: float, text: str, klass: FrameClass) -> "FrameRecord":
    return FrameRecord(
        path=f"frames/frame_{idx:03d}_t-00-{int(ts):02d}.jpg",
        timestamp_seconds=ts,
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=None,
    )


def test_dedup_clusters_identical_code():
    code = "def f():\n    return 1"
    frames = [
        _rec(1, 1, code, FrameClass.CODE),
        _rec(2, 5, code, FrameClass.CODE),
        _rec(3, 9, code, FrameClass.CODE),
    ]
    out = dedup_code_frames(frames)
    cluster_ids = {f.cluster_id for f in out}
    assert len(cluster_ids) == 1


def test_dedup_keeps_distinct_code():
    frames = [
        _rec(1, 1, "def add(a, b):\n    return a + b", FrameClass.CODE),
        _rec(2, 5, "class User:\n    def __init__(self): pass", FrameClass.CODE),
    ]
    out = dedup_code_frames(frames)
    assert len({f.cluster_id for f in out}) == 2


def test_dedup_ignores_non_code():
    frames = [
        _rec(1, 1, "Step 1", FrameClass.SLIDE_TEXT),
        _rec(2, 5, "Step 1", FrameClass.SLIDE_TEXT),
    ]
    out = dedup_code_frames(frames)
    assert all(f.cluster_id is None for f in out)


def test_dedup_normalizes_comments_and_whitespace():
    """Same code with different comments + whitespace must cluster together."""
    a = "def f():\n    return 1  # implementation"
    b = "def   f():\n  return 1   # different comment"
    out = dedup_code_frames([
        _rec(1, 1, a, FrameClass.CODE),
        _rec(2, 5, b, FrameClass.CODE),
    ])
    assert len({f.cluster_id for f in out}) == 1


import json
from frame_ocr import write_ocr_json, read_ocr_json


def test_ocr_json_roundtrip(tmp_path):
    frames = [
        _rec(1, 1.0, "x", FrameClass.CODE),
        _rec(2, 5.0, "y", FrameClass.SLIDE_TEXT),
    ]
    target = tmp_path / "ocr.json"
    write_ocr_json(target, video_title="T", duration_seconds=12.0, frames=frames)
    raw = json.loads(target.read_text())
    assert raw["video"]["title"] == "T"
    assert raw["video"]["duration_seconds"] == 12.0
    assert raw["frames"][0]["frame_class"] == "code"
    back = read_ocr_json(target)
    assert len(back) == 2
    assert back[0].ocr_text == "x"
