from extract import _grade_ocr, _grade_frame_coverage


def test_grade_ocr_buckets():
    assert _grade_ocr(0.9) == "high"
    assert _grade_ocr(0.75) == "medium"
    assert _grade_ocr(0.5) == "low"
    assert _grade_ocr(None) == "none"


def test_grade_frame_coverage():
    # selected_non_code / duration_minutes
    assert _grade_frame_coverage(20, duration_seconds=60) == "high"
    assert _grade_frame_coverage(2, duration_seconds=600) == "low"
