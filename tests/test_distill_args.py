import distill
from enrichment import TranscriptSegment
from frame_ocr import FrameClass, FrameRecord


def test_parse_args_minimal():
    ns = distill._parse_args(["My_Title", "coding_agent"])
    assert ns.title == "My_Title"
    assert ns.style == "coding_agent"
    assert ns.dry_run_payload is False


def test_parse_args_flags():
    ns = distill._parse_args(["X", "y", "--model", "gpt-4o", "--max-vision-frames", "8", "--dry-run-payload", "--force"])
    assert ns.model == "gpt-4o"
    assert ns.max_vision_frames == 8
    assert ns.dry_run_payload is True
    assert ns.force is True


def _seg(text: str) -> TranscriptSegment:
    return TranscriptSegment(seg_id=0, start=0.0, end=5.0, text=text)


def _frame(text: str, klass: FrameClass) -> FrameRecord:
    return FrameRecord(
        path="frames/frame_001_t-00-01.jpg",
        timestamp_seconds=1.0,
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id="c0" if klass == FrameClass.CODE else None,
    )


def test_route_style_preserves_explicit_style():
    style, profile = distill._route_style(
        "coding_agent",
        title="Anything",
        segments=[_seg("cut plywood and drill holes")],
        frames=[],
    )

    assert style == "coding_agent"
    assert profile is None


def test_route_style_auto_uses_video_profile():
    style, profile = distill._route_style(
        "auto",
        title="Build a FastAPI coding agent",
        segments=[_seg("Install the SDK, create app.py, define a function, and run uv run pytest.")],
        frames=[_frame("def app():\n    return client.chat.completions.create()", FrameClass.CODE)],
    )

    assert style == "coding_agent"
    assert profile is not None
    assert profile.recommended_style == "coding_agent"


def test_invalid_explicit_style_fails_before_doctor(tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "Video"
    out_dir.mkdir()
    (out_dir / distill.MANIFEST_FILENAME).write_text("{}")
    monkeypatch.setattr(distill, "doctor", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("doctor called")))

    rc = distill.main([str(out_dir), "missing_style", "--dry-run-payload"])

    assert rc == 1
    assert "style 'missing_style' not found" in capsys.readouterr().err
