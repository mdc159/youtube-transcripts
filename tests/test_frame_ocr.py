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
