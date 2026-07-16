from yt_distill.core.enrichment import enrich_transcript, TranscriptSegment
from yt_distill.stages.frame_ocr import FrameRecord, FrameClass


def _seg(i, start, end, text):
    return TranscriptSegment(seg_id=i, start=start, end=end, text=text)


def _frame(i, ts, text, klass=FrameClass.CODE, cluster=None):
    return FrameRecord(
        path=f"frames/frame_{i:03d}_t-{int(ts // 60):02d}-{int(ts % 60):02d}.jpg",
        timestamp_seconds=ts,
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=cluster,
    )


def test_inserts_code_block_after_containing_segment():
    segs = [_seg(0, 0.0, 5.0, "intro"), _seg(1, 5.0, 10.0, "lets see code")]
    frames = [_frame(7, 7.0, "def f(): pass")]
    out = enrich_transcript(segs, frames)
    assert "lets see code" in out
    assert "def f(): pass" in out
    assert out.index("def f(): pass") > out.index("lets see code")


def test_inserts_at_boundary_when_no_containing_segment():
    segs = [_seg(0, 0.0, 5.0, "a"), _seg(1, 8.0, 10.0, "b")]
    frames = [_frame(7, 6.5, "code", FrameClass.CODE)]
    out = enrich_transcript(segs, frames)
    assert "code" in out
    # code should appear between segment 0 and segment 1
    assert out.index("code") > out.index("a") and out.index("code") < out.index("b")


def test_slide_text_uses_quoted_format():
    segs = [_seg(0, 0.0, 10.0, "x")]
    frames = [_frame(5, 5.0, "Slide title here", FrameClass.SLIDE_TEXT)]
    out = enrich_transcript(segs, frames)
    assert "> [slide" in out
    assert "Slide title here" in out
