"""Unit tests for skill_bundle.py (slug / frontmatter / assets / reference / provenance)."""
from __future__ import annotations

import json
from pathlib import Path

from yt_distill.output.skill_bundle import (
    _extract_trigger_description,
    slugify,
    write_skill_bundle,
)


def test_slugify():
    assert slugify("Unreal_Engine_5_for_Architects") == "unreal-engine-5-for-architects"
    assert slugify("  Weird!!  Título  ") == "weird-t-tulo"
    assert slugify("") == "skill"
    assert len(slugify("x" * 200)) <= 60


def test_trigger_description_from_section():
    md = (
        "### 1. When To Use This Skill\n\n"
        "Build archviz walkthroughs in UE5.\nUse when presenting projects.\n\n"
        "### 2. Prerequisites\n- UE 5.3\n"
    )
    assert _extract_trigger_description(md) == (
        "Build archviz walkthroughs in UE5. Use when presenting projects.")


def test_trigger_description_fallback_first_paragraph():
    md = "# Title\n\nSome body paragraph here.\n\n### 2. Prerequisites\n"
    assert _extract_trigger_description(md) == "Some body paragraph here."


SKILL_MD = """### 1. When To Use This Skill

Recreate the UE5 archviz workflow.

### 5. Lessons

1. **Action**: Set Final Gather Quality to 4.0 (frame_001_t-00-05, seg#0)
   status: distilled
2. **Action**: Import the model (frame_002)
   status: distilled
"""


def _make_artifact_dir(tmp_path: Path) -> tuple[Path, dict]:
    out_dir = tmp_path / "Test_Video"
    frames = out_dir / "frames"
    frames.mkdir(parents=True)
    (frames / "frame_001_t-00-05.jpg").write_bytes(b"jpg1")
    (frames / "frame_002_t-00-09.jpg").write_bytes(b"jpg2")
    (frames / "frame_003_t-00-12.jpg").write_bytes(b"jpg3")  # uncited
    manifest_data = {
        "source_id": "yt:abc123def45",
        "source_url": "https://youtu.be/abc123def45",
        "title": "Test_Video",
        "duration_seconds": 100.0,
        "extract": {"transcript_source": "yt-dlp", "transcript_quality": "high"},
    }
    return out_dir, manifest_data


def test_write_skill_bundle_full(tmp_path):
    out_dir, manifest_data = _make_artifact_dir(tmp_path)

    # references.json + refs tree (snapshotted repo + fetched doc)
    snap = out_dir / "refs" / "foo__bar@abcabcabcabc"
    (snap / "snapshot").mkdir(parents=True)
    (snap / "snapshot" / "README.md").write_text("# bar\n")
    docs = out_dir / "refs" / "docs"
    docs.mkdir(parents=True)
    (docs / "aaaa_guide.md").write_text("guide\n")
    (out_dir / "refs" / "source_meta.json").write_text(json.dumps({"upload_date": "20260101"}))
    (out_dir / "references.json").write_text(json.dumps({
        "references": [
            {"url": "https://github.com/foo/bar", "kind": "github_repo",
             "status": "snapshotted",
             "detail": {"clone_url": "https://github.com/foo/bar.git",
                        "sha": "abcabcabcabcabcabcabcabcabcabcabcabcabca",
                        "clone_date": "2026-01-01T00:00:00Z",
                        "snapshot_dir": "foo__bar@abcabcabcabc"}},
            {"url": "https://docs.example.com/guide", "kind": "docs",
             "status": "fetched", "detail": {"path": "refs/docs/aaaa_guide.md"}},
        ],
    }))

    distill_result = {"model_profile": "gemini-3-flash", "prompt_contract_version": 1,
                      "quality": {"transcript": "high"}}
    bundle = write_skill_bundle(
        out_dir, skill_md=SKILL_MD, distill_result=distill_result,
        manifest_data=manifest_data, unresolved_citations=["seg#999"])

    assert bundle == out_dir / "skills" / "test-video"

    # SKILL.md: frontmatter + body
    text = (bundle / "SKILL.md").read_text()
    assert text.startswith("---\nname: test-video\n")
    assert 'description: "Recreate the UE5 archviz workflow."' in text
    assert "Final Gather Quality" in text

    # assets: only cited frames (001 full-form, 002 short-form; 003 excluded)
    assets = sorted(p.name for p in (bundle / "assets").iterdir())
    assert assets == ["frame_001_t-00-05.jpg", "frame_002_t-00-09.jpg"]

    # reference: repo snapshot + doc + sources.json with pinned SHA
    assert (bundle / "reference" / "foo__bar@abcabcabcabc" / "snapshot" / "README.md").exists()
    assert (bundle / "reference" / "docs" / "aaaa_guide.md").exists()
    sources = json.loads((bundle / "reference" / "sources.json").read_text())
    assert sources["repo_pointers"][0]["sha"].startswith("abcabc")

    # provenance
    prov = json.loads((bundle / "provenance.json").read_text())
    assert prov["status"] == "distilled"
    assert prov["review_iterations"] == []
    assert prov["unresolved_gaps"] == ["seg#999"]
    assert prov["video_upload_date"] == "20260101"
    assert prov["assets_packaged"] == ["frame_001_t-00-05.jpg", "frame_002_t-00-09.jpg"]


def test_write_skill_bundle_minimal_no_refs_no_frames(tmp_path):
    out_dir = tmp_path / "Bare"
    out_dir.mkdir()
    manifest_data = {"source_id": "yt:x", "source_url": "u", "title": "Bare",
                     "duration_seconds": 1.0, "extract": None}
    bundle = write_skill_bundle(
        out_dir, skill_md="Just a body.", distill_result={},
        manifest_data=manifest_data)
    assert (bundle / "SKILL.md").read_text().startswith("---\nname: bare\n")
    assert not (bundle / "assets").exists()
    assert not (bundle / "reference").exists()
    prov = json.loads((bundle / "provenance.json").read_text())
    assert prov["unresolved_gaps"] == []


def test_rewrite_supersedes_previous_bundle(tmp_path):
    out_dir, manifest_data = _make_artifact_dir(tmp_path)
    b1 = write_skill_bundle(out_dir, skill_md=SKILL_MD, distill_result={},
                            manifest_data=manifest_data)
    stale = b1 / "assets" / "stale.jpg"
    assert stale.exists() is False  # assets exist but not this file
    (b1 / "leftover.txt").write_text("old")
    b2 = write_skill_bundle(out_dir, skill_md="New body.", distill_result={},
                            manifest_data=manifest_data)
    assert b2 == b1
    assert not (b2 / "leftover.txt").exists()
    assert "New body." in (b2 / "SKILL.md").read_text()
