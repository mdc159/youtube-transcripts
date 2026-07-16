"""Renderer tests for the markdown-passthrough path.

Regression: when the LLM returns full markdown (its actual mode under the
contract) the renderer used to wrap it in another `## Summary` heading and
leak `## Summary` into the frontmatter `summary:` field.
"""
from yt_distill.output.render import render_markdown, render_passthrough


_MODEL_MARKDOWN = """## Summary
The video walks through installing Hermes Agent on WSL2 and running a competitor research task.

## Key Points
- Hermes is stateful and learns from every interaction (`seg#57`).
- Works with multiple model providers (`seg#37`).

## Steps / Walkthrough
1. Install WSL2 (`seg#117`).
2. Run the installer (`seg#160`).
"""


def _base(summary: str) -> dict:
    return {
        "schema_version": 1,
        "source_id": "yt:abc",
        "title": "Demo",
        "model_profile": "gemini-3-flash",
        "prompt_contract_version": 1,
        "summary": summary,
        "quality": {
            "transcript": "high",
            "ocr": "high",
            "frame_coverage": "high",
            "distillation_confidence": "high",
        },
        "warnings": [],
        "token_usage": {"prompt": 1, "completion": 1, "image_count": 0},
        "citations": {"segments_referenced": 3, "frames_referenced": 0, "unresolved": 0},
    }


def test_passthrough_emits_single_summary_heading():
    md = render_passthrough(_base(_MODEL_MARKDOWN), style_name="human_tutorial", today_iso="2026-05-10")
    assert md.count("## Summary") == 1, "passthrough must not double-stamp the Summary heading"


def test_passthrough_preserves_all_model_sections():
    md = render_passthrough(_base(_MODEL_MARKDOWN), style_name="human_tutorial", today_iso="2026-05-10")
    body = md.split("---\n", 2)[-1]
    assert "## Key Points" in body
    assert "## Steps / Walkthrough" in body
    assert "Install WSL2" in body


def test_passthrough_frontmatter_summary_uses_real_prose_not_heading():
    md = render_passthrough(_base(_MODEL_MARKDOWN), style_name="human_tutorial", today_iso="2026-05-10")
    fm_lines = md.split("---\n", 2)[1].splitlines()
    summary_line = next(l for l in fm_lines if l.startswith("summary:"))
    assert "## Summary" not in summary_line, "frontmatter summary must not contain a markdown heading"
    assert "Hermes Agent" in summary_line or "WSL2" in summary_line, (
        f"frontmatter summary should preview the real prose; got: {summary_line!r}"
    )


def test_passthrough_arbitrary_style_section_names():
    """Style-driven structure: the model emits whatever sections the style asked for."""
    tutorial_md = """## Introduction
Welcome! In this tutorial you'll learn to set up Hermes (`seg#0`).

## Prerequisites
- WSL2 (Windows users)
- Python 3.11

## Step-by-Step Instructions
### Step 1: Prepare your environment
**Goal:** Get a working WSL2 install.
**Action:** Run `wsl --install` in PowerShell as admin (`seg#117`).
"""
    md = render_passthrough(_base(tutorial_md), style_name="human_tutorial", today_iso="2026-05-10")
    body = md.split("---\n", 2)[-1]
    assert "## Introduction" in body
    assert "## Prerequisites" in body
    assert "## Step-by-Step Instructions" in body


def test_passthrough_writes_unresolved_citation_banner():
    data = _base(_MODEL_MARKDOWN)
    data["citations"]["unresolved"] = 2
    md = render_passthrough(data, style_name="human_tutorial", today_iso="2026-05-10")
    assert "unresolved citations" in md.lower()


def test_passthrough_includes_frontmatter_metadata():
    md = render_passthrough(_base(_MODEL_MARKDOWN), style_name="human_tutorial", today_iso="2026-05-10")
    assert "model_profile: gemini-3-flash" in md
    assert "prompt_contract_version: 1" in md
    assert "human_tutorial" in md


def test_existing_render_markdown_still_works_with_structured_json():
    """Backward compat: when the model returns parseable JSON with key_points etc.,
    the structured renderer should still produce the canonical sections."""
    data = _base("Just a short summary.")
    data["key_points"] = [{"text": "K1", "citations": ["seg#1"]}]
    md = render_markdown(data, style_name="coding_agent", today_iso="2026-05-10")
    assert "## Summary" in md
    assert md.count("## Summary") == 1, "structured renderer should also not double-stamp"
    assert "## Key Points" in md
    assert "K1" in md
