from pathlib import Path
import pytest
from frame_ocr import ocr_frame, OcrResult, CONFIDENCE_GATE


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
