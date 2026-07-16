from yt_distill.output.render import render_markdown


def test_render_includes_required_sections():
    data = {
        "schema_version": 1,
        "source_id": "yt:abc",
        "title": "Demo",
        "model_profile": "gemini-3-flash",
        "prompt_contract_version": 1,
        "summary": "It's a demo.",
        "key_points": [{"text": "K1", "citations": ["seg#1"]}],
        "steps": [],
        "code_blocks": [{"language": "python", "code": "print(1)", "citations": ["frame_001_t-00-05"], "approximate": False}],
        "tools_mentioned": [],
        "open_questions": [],
        "visual_evidence_used": [{"frame_id": "frame_010_t-01-00", "class": "diagram", "interpretation": "arch", "selection_reason": "scene_change"}],
        "quality": {"transcript": "high", "ocr": "medium", "frame_coverage": "high", "distillation_confidence": "medium"},
        "warnings": [],
        "token_usage": {"prompt": 1, "completion": 1, "image_count": 1},
        "citations": {"segments_referenced": 1, "frames_referenced": 1, "unresolved": 0},
    }
    md = render_markdown(data, style_name="coding_agent", today_iso="2026-05-07")
    assert "## Summary" in md
    assert "## Key Points" in md
    assert "## Code" in md
    assert "## Visual Evidence Used" in md
    assert "model_profile: gemini-3-flash" in md  # frontmatter
    assert "prompt_contract_version: 1" in md
