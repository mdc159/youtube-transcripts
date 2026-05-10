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


def test_parse_args_audience_note():
    ns = distill._parse_args(["X", "y", "--audience-note", "Intermediate Python devs evaluating tools."])
    assert ns.audience_note == "Intermediate Python devs evaluating tools."


def test_parse_args_audience_note_missing_defaults_none():
    ns = distill._parse_args(["X", "y"])
    assert ns.audience_note is None


def test_compose_style_with_audience_note_prepends_block():
    style_md = "# Human Tutorial Style Guide\n\n## Output Format\n\n### 1. Introduction\n..."
    out = distill._compose_style_with_audience(style_md, audience_note="DIY makers, no Python.")
    assert "## Audience Profile" in out
    assert "DIY makers, no Python." in out
    # The original style content must follow the audience block, not be replaced.
    assert out.endswith(style_md) or style_md in out
    assert out.index("Audience Profile") < out.index("Human Tutorial Style Guide")


def test_compose_style_without_audience_note_returns_style_unchanged():
    style_md = "## Output Format\n\n### 1. Step\n"
    assert distill._compose_style_with_audience(style_md, audience_note=None) == style_md
    assert distill._compose_style_with_audience(style_md, audience_note="") == style_md
    assert distill._compose_style_with_audience(style_md, audience_note="   \n  ") == style_md


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
