"""Tests for the enrich.py post-processor (Tier 1: deterministic).

Tier 2 LLM-call functions live in separate tests with mocked clients.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import enrich


# --- 1C: youtube deep-links --------------------------------------------------

def test_deep_link_t_equals_format():
    md = "Open the chat (`t=05:23`)."
    out = enrich._yt_deep_link_timestamps(md, source_url="https://www.youtube.com/watch?v=abc123")
    assert "[`t=05:23`](https://www.youtube.com/watch?v=abc123&t=323s)" in out


def test_deep_link_t_range_takes_start():
    md = "Setup wizard (`t=02:00–03:30`)."
    out = enrich._yt_deep_link_timestamps(md, source_url="https://www.youtube.com/watch?v=abc")
    assert "t=120s" in out, "range should deep-link to the start timestamp"


def test_deep_link_idempotent():
    md = "See `t=01:05`."
    once = enrich._yt_deep_link_timestamps(md, source_url="https://www.youtube.com/watch?v=abc")
    twice = enrich._yt_deep_link_timestamps(once, source_url="https://www.youtube.com/watch?v=abc")
    assert once == twice, "running twice must produce the same markdown"


def test_deep_link_skips_when_no_source_url():
    md = "See `t=01:05`."
    assert enrich._yt_deep_link_timestamps(md, source_url="") == md


def test_deep_link_uses_youtu_be_short_form():
    md = "See `t=00:30`."
    out = enrich._yt_deep_link_timestamps(md, source_url="https://youtu.be/abc123")
    assert "youtu.be/abc123?t=30s" in out


# --- 1A: inline frame embedding ----------------------------------------------

def _make_dir_with_frames(tmp_path: Path, frame_names: list[str]) -> Path:
    out = tmp_path / "vid"
    (out / "frames").mkdir(parents=True)
    for n in frame_names:
        (out / "frames" / n).write_bytes(b"fake jpg")
    return out


def test_inline_frame_inserts_obsidian_image_after_citation(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, ["frame_004_t-00-36.jpg"])
    md = "Step 1 (`frame_004_t-00-36`).\n\nStep 2."
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    assert "![frame_004_t-00-36](frames/frame_004_t-00-36.jpg)" in new
    assert "Step 1" in new and "Step 2" in new


def test_inline_frame_handles_short_form(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, ["frame_023_t-04-25.jpg"])
    md = "See `frame_023` for the diagram."
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    assert "![frame_023" in new
    assert "frames/frame_023_t-04-25.jpg" in new


def test_inline_frame_idempotent(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, ["frame_001_t-00-00.jpg"])
    md = "Welcome (`frame_001_t-00-00`)."
    once = enrich._inline_frame_images(md, out_dir=out_dir)
    twice = enrich._inline_frame_images(once, out_dir=out_dir)
    assert once == twice, "no double embeds on second pass"


def test_inline_frame_skips_missing_file(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, [])
    md = "See (`frame_999_t-99-99`)."
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    assert "![" not in new, "should not embed a non-existent frame"


def test_inline_frame_only_first_occurrence_per_id(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, ["frame_010_t-02-00.jpg"])
    md = "Talk about `frame_010_t-02-00`. Later again `frame_010_t-02-00`."
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    assert new.count("![frame_010_t-02-00]") == 1, "embed each frame at most once"


def test_inline_frame_skips_inside_fenced_code_block(tmp_path):
    """Regression: frame citations inside ```...``` blocks must NOT receive an
    embed; otherwise the embed lands inside the code block and breaks rendering.
    """
    out_dir = _make_dir_with_frames(tmp_path, ["frame_034_t-06-38.jpg"])
    md = """Some prose.

```bash
# Comment referencing frame_034_t-06-38
mkdir foo
```

After block."""
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    bash_block = new.split("```bash", 1)[1].split("```", 1)[0]
    assert "![frame_034_t-06-38]" not in bash_block, (
        "embed leaked into fenced code block — would corrupt rendering"
    )


def test_inline_frame_skips_inside_indented_fenced_block(tmp_path):
    """Regression: fenced code blocks inside list items (indented fences) must
    also be detected. CommonMark allows the fence to be indented to match the
    enclosing list item's content column.
    """
    out_dir = _make_dir_with_frames(tmp_path, ["frame_038_t-07-26.jpg"])
    md = """3. **Extract prompts**
    - **Code/Command**:
      ```python
      # frame_038 observation: Running an extraction script
      python extract-claude-prompts.py
      ```
    - **Explanation**: It pulls only the prompts.
"""
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    code_section = new.split("```python", 1)[1].split("```", 1)[0]
    assert "![frame_038" not in code_section, (
        "indented fenced block must also be skipped"
    )


def test_inline_frame_still_embeds_when_only_inline_code_backticks(tmp_path):
    """Inline backticks (single backtick spans) are NOT code fences; embeds
    around them should still happen."""
    out_dir = _make_dir_with_frames(tmp_path, ["frame_005_t-00-30.jpg"])
    md = "Run `python foo.py` after seeing `frame_005_t-00-30`."
    new = enrich._inline_frame_images(md, out_dir=out_dir)
    assert "![frame_005_t-00-30]" in new


# --- 1B: visual evidence gallery ---------------------------------------------

def test_gallery_includes_each_selected_frame(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, ["frame_001_t-00-00.jpg", "frame_010_t-02-00.jpg"])
    selected = {
        "selected": [
            {"path": "frames/frame_001_t-00-00.jpg", "frame_class": "slide_text", "reason": "scene_change"},
            {"path": "frames/frame_010_t-02-00.jpg", "frame_class": "diagram", "reason": "anchor"},
        ]
    }
    interpretations = {
        "frame_001_t-00-00": "Title slide",
        "frame_010_t-02-00": "Compounding loop diagram",
    }
    section = enrich._build_visual_gallery(selected, interpretations=interpretations)
    assert "## Visual Evidence Gallery" in section
    assert "frame_001_t-00-00" in section and "Title slide" in section
    assert "frame_010_t-02-00" in section and "Compounding loop" in section
    assert "![" in section, "gallery must embed thumbnails"


def test_gallery_omitted_when_no_selected(tmp_path):
    out_dir = _make_dir_with_frames(tmp_path, [])
    section = enrich._build_visual_gallery({"selected": []}, interpretations={})
    assert section == ""


# --- 1D: code-cluster appendix -----------------------------------------------

def test_code_appendix_groups_by_cluster_id():
    ocr = {
        "frames": [
            {
                "path": "frames/frame_050_t-10-00.jpg",
                "frame_class": "code",
                "cluster_id": "c0",
                "ocr_text": "def hello():\n    print('hi')",
                "ocr_confidence": 0.92,
            },
            {
                "path": "frames/frame_051_t-10-05.jpg",
                "frame_class": "code",
                "cluster_id": "c0",
                "ocr_text": "def hello():\n    print('hi')\n    return 0",
                "ocr_confidence": 0.95,
            },
            {
                "path": "frames/frame_080_t-15-00.jpg",
                "frame_class": "code",
                "cluster_id": "c1",
                "ocr_text": "import json",
                "ocr_confidence": 0.88,
            },
        ]
    }
    section = enrich._build_code_appendix(ocr)
    assert "## Source Code" in section
    assert "cluster_id=c0" in section
    assert "cluster_id=c1" in section
    assert "~approximate" in section, "code from OCR must be tagged ~approximate per the contract"
    assert "import json" in section
    assert "def hello()" in section


def test_code_appendix_omitted_when_no_code_frames():
    ocr = {"frames": [{"path": "frames/x.jpg", "frame_class": "slide_text", "ocr_text": "hi"}]}
    assert enrich._build_code_appendix(ocr) == ""


# --- Tier 2: LLM-driven sections (mocked) ------------------------------------

class _StubProfile:
    name = "stub"
    model = "stub-model"
    base_url = "http://localhost"
    api_key_env = "STUB_KEY"


def test_mermaid_pipeline_extracts_steps_and_inserts_block(monkeypatch):
    md = """## Step-by-Step Instructions

### 1. Install
**Action:** Run installer.

### 2. Configure
**Action:** Set keys.
"""
    captured = {}
    def fake_call(profile, prompt):
        captured["prompt"] = prompt
        return "```mermaid\nflowchart TD\n    s1[Install] --> s2[Configure]\n```"
    monkeypatch.setattr(enrich, "_call_llm", fake_call)

    out = enrich._mermaid_pipeline_from_steps(md, profile=_StubProfile())
    assert "```mermaid" in out
    assert "flowchart TD" in out
    assert "Install" in captured["prompt"] and "Configure" in captured["prompt"], (
        "the prompt must include the actual steps section"
    )


def test_mermaid_pipeline_returns_empty_if_section_missing(monkeypatch):
    monkeypatch.setattr(enrich, "_call_llm", lambda *a, **k: pytest.fail("should not call LLM"))
    assert enrich._mermaid_pipeline_from_steps("# nope", profile=_StubProfile()) == ""


def test_reference_tables_only_calls_llm_when_dense_slides_exist(monkeypatch):
    ocr = {
        "frames": [
            {"path": "frames/a.jpg", "frame_class": "slide_text", "ocr_text": "x" * 500},
            {"path": "frames/b.jpg", "frame_class": "ui", "ocr_text": "y" * 800},
            {"path": "frames/c.jpg", "frame_class": "slide_text", "ocr_text": "short"},
        ]
    }
    seen = {}
    def fake_call(profile, prompt):
        seen["prompt"] = prompt
        return "### Tools\n| name | purpose |\n|---|---|\n| foo | bar |"
    monkeypatch.setattr(enrich, "_call_llm", fake_call)
    out = enrich._reference_tables_from_slides(ocr, profile=_StubProfile())
    assert "## Reference Tables" in out
    assert "frames/a.jpg".replace("frames/", "") in seen["prompt"] or "a" in seen["prompt"]
    # Only the dense slide_text frame should have been included; UI and short
    # slide_text are filtered out.
    assert "y" * 800 not in seen["prompt"]
    assert "x" * 500 in seen["prompt"]


def test_reference_tables_handles_NONE_response(monkeypatch):
    ocr = {"frames": [{"path": "frames/a.jpg", "frame_class": "slide_text", "ocr_text": "x" * 500}]}
    monkeypatch.setattr(enrich, "_call_llm", lambda *a, **k: "NONE")
    assert enrich._reference_tables_from_slides(ocr, profile=_StubProfile()) == ""


def test_mindmap_extracts_concepts_section(monkeypatch):
    md = """## Core Concepts

- **Stateful Design:** captures trajectory.
- **Provider Agnosticism:** swap models.
"""
    captured = {}
    def fake_call(profile, prompt):
        captured["prompt"] = prompt
        return "```mermaid\nmindmap\n  root((Topic))\n    Stateful\n    Providers\n```"
    monkeypatch.setattr(enrich, "_call_llm", fake_call)
    out = enrich._mindmap_from_concepts(md, profile=_StubProfile())
    assert "```mermaid" in out and "mindmap" in out
    assert "Stateful" in captured["prompt"]


# --- Public orchestrator: end-to-end on a fixture dir ------------------------

def _seed_fixture(tmp_path: Path, *, source_url: str = "https://youtu.be/abc123") -> Path:
    out = tmp_path / "MyVideo"
    (out / "frames").mkdir(parents=True)
    (out / "frames" / "frame_001_t-00-00.jpg").write_bytes(b"fake")
    (out / "frames" / "frame_010_t-02-00.jpg").write_bytes(b"fake")
    (out / "extract_meta.json").write_text(json.dumps({"source_url": source_url, "duration_seconds": 600}))
    (out / "ocr.json").write_text(json.dumps({
        "frames": [
            {
                "path": "frames/frame_001_t-00-00.jpg",
                "frame_class": "slide_text",
                "ocr_text": "Title slide",
                "ocr_confidence": 0.9,
            },
            {
                "path": "frames/frame_010_t-02-00.jpg",
                "frame_class": "code",
                "cluster_id": "c0",
                "ocr_text": "print('hi')",
                "ocr_confidence": 0.95,
            },
        ]
    }))
    (out / "selected_frames.json").write_text(json.dumps({
        "selected": [
            {"path": "frames/frame_001_t-00-00.jpg", "frame_class": "slide_text", "reason": "anchor"},
            {"path": "frames/frame_010_t-02-00.jpg", "frame_class": "code", "reason": "scene_change"},
        ]
    }))
    (out / "MyVideo_human_tutorial.md").write_text("""---
type: tutorial
---

## Introduction
See `frame_001_t-00-00`. Open at `t=00:30`.

## Core Concepts
- **Thing:** matters.
""")
    return out


def test_enrich_no_llm_inlines_frames_and_links(tmp_path):
    out = _seed_fixture(tmp_path)
    enrich.enrich(out, style_name="human_tutorial", profile=None,
                  do_mermaid=False, do_tables=False, do_mindmap=False)
    md = (out / "MyVideo_human_tutorial.md").read_text()
    assert "![frame_001_t-00-00](frames/frame_001_t-00-00.jpg)" in md
    assert "https://youtu.be/abc123?t=30s" in md
    assert "## Visual Evidence Gallery" in md
    assert "## Source Code (verbatim from frames)" in md


def test_enrich_is_idempotent(tmp_path):
    out = _seed_fixture(tmp_path)
    enrich.enrich(out, style_name="human_tutorial", profile=None,
                  do_mermaid=False, do_tables=False, do_mindmap=False)
    once = (out / "MyVideo_human_tutorial.md").read_text()
    enrich.enrich(out, style_name="human_tutorial", profile=None,
                  do_mermaid=False, do_tables=False, do_mindmap=False)
    twice = (out / "MyVideo_human_tutorial.md").read_text()
    assert once == twice, "enrich must be idempotent"

