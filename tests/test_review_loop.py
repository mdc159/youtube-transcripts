"""Unit tests for review_loop.py — reviewer parsing, escalation, loop control."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import review_loop as rl
from yt_distill.core.manifest import Manifest
from skill_bundle import write_skill_bundle


# ---------------------------------------------------------------------------
# helpers / parsing
# ---------------------------------------------------------------------------

def test_parse_reviewer_json_plain():
    data = rl._parse_reviewer_json('{"verdict": "pass"}')
    assert data == {"verdict": "pass", "blocking_gaps": [], "minor_gaps": []}


def test_parse_reviewer_json_fenced_with_prose():
    raw = 'Here you go:\n```json\n{"blocking_gaps": [{"where": "L1"}]}\n```'
    data = rl._parse_reviewer_json(raw)
    assert data["verdict"] == "gaps"
    assert data["blocking_gaps"][0]["where"] == "L1"


@pytest.mark.parametrize("value,expected", [
    ("1:34:02", 5642.0),
    ("t=05:23", 323.0),
    ("619:23", 37163.0),
    ("90", 90.0),
    ("nonsense", None),
])
def test_parse_timestamp(value, expected):
    assert rl._parse_timestamp(value) == expected


# ---------------------------------------------------------------------------
# fixture: artifact dir + bundle
# ---------------------------------------------------------------------------

SKILL_MD = """### 1. When To Use This Skill

Build the demo scene.

### 5. Lessons

1. **Action**: Set quality to the value shown (seg#0)
   status: distilled
"""


@pytest.fixture()
def artifact(tmp_path):
    out_dir = tmp_path / "Test_Video"
    out_dir.mkdir()
    (out_dir / "Test_Video_formatted_transcript.txt").write_text(
        "0.0|set the final gather quality to four\n"
        "5.0|now we import the model\n"
        "10.0|and we press render\n")
    m = Manifest.load_or_create(
        out_dir, source_id="yt:abc123def45", source_url="https://youtu.be/abc123def45",
        title="Test_Video", duration_seconds=15.0)
    m.set_extract({"transcript_source": "yt-dlp", "transcript_quality": "high", "files": {}})
    m.save()
    write_skill_bundle(out_dir, skill_md=SKILL_MD,
                       distill_result={"model_profile": "test"},
                       manifest_data=m.data)
    return out_dir


PASS = json.dumps({"verdict": "pass", "blocking_gaps": [], "minor_gaps": []})
GAPS = json.dumps({
    "verdict": "gaps",
    "blocking_gaps": [
        {"where": "Lesson 1 step 1", "what_is_missing": "the exact quality value",
         "likely_source": {"kind": "transcript", "value": "final gather quality"}},
    ],
    "minor_gaps": [],
})


def _fake_llm(responses: list[str]):
    """Dispatch: reviewer calls pop from `responses`; synth returns revised md."""
    state = {"i": 0}

    def call(profile, system, user):
        if system is rl.REVIEWER_PROMPT or "fresh agent" in system:
            resp = responses[min(state["i"], len(responses) - 1)]
            state["i"] += 1
            return resp
        return SKILL_MD.replace("the value shown", "**4.0** (t=00:00)")

    return call


# ---------------------------------------------------------------------------
# loop behavior
# ---------------------------------------------------------------------------

def test_immediate_pass_marks_complete(artifact, monkeypatch):
    monkeypatch.setattr(rl, "_call_llm", _fake_llm([PASS]))
    rc = rl.main([str(artifact)])
    assert rc == 0
    prov = json.loads((artifact / "skills" / "test-video" / "provenance.json").read_text())
    assert prov["status"] == "complete"
    assert len(prov["review_iterations"]) == 1
    assert prov["review_iterations"][0]["resolved"] is True
    manifest = json.loads((artifact / "artifact_manifest.json").read_text())
    assert manifest["distill_runs"][0]["phase"] == "review_loop"
    assert manifest["distill_runs"][0]["status"] == "complete"


def test_gap_then_pass_resynthesizes(artifact, monkeypatch):
    monkeypatch.setattr(rl, "_call_llm", _fake_llm([GAPS, PASS]))
    rc = rl.main([str(artifact)])
    assert rc == 0
    bundle = artifact / "skills" / "test-video"
    skill = (bundle / "SKILL.md").read_text()
    assert "**4.0**" in skill  # revision applied
    prov = json.loads((bundle / "provenance.json").read_text())
    assert prov["status"] == "complete"
    assert len(prov["review_iterations"]) == 2
    # iteration 1 logged the transcript escalation
    assert prov["review_iterations"][0]["escalations"]["transcript_windows"] >= 1


def test_cap_ships_incomplete_with_residual_gaps(artifact, monkeypatch):
    monkeypatch.setattr(rl, "_call_llm", _fake_llm([GAPS, GAPS, GAPS]))
    rc = rl.main([str(artifact), "--max-iterations", "2"])
    assert rc == 0
    prov = json.loads((artifact / "skills" / "test-video" / "provenance.json").read_text())
    assert prov["status"] == "incomplete"
    assert len(prov["review_iterations"]) == 2
    assert prov["residual_gaps"][0]["what_is_missing"] == "the exact quality value"
    manifest = json.loads((artifact / "artifact_manifest.json").read_text())
    assert manifest["distill_runs"][0]["status"] == "incomplete"
    assert manifest["distill_runs"][0]["residual_gap_count"] == 1


def test_requires_bundle(artifact):
    import shutil
    shutil.rmtree(artifact / "skills")
    with pytest.raises(RuntimeError, match="claude_skill"):
        rl.main([str(artifact)])


# ---------------------------------------------------------------------------
# escalation units
# ---------------------------------------------------------------------------

def test_escalate_transcript_window(artifact):
    gaps = [{"where": "L1", "what_is_missing": "value",
             "likely_source": {"kind": "transcript", "value": "gather quality"}}]
    evidence, stats = rl.escalate(gaps, artifact, source_url="", max_frame_grabs=0)
    assert stats.transcript_windows == 1
    assert "seg#0" in evidence
    assert "final gather quality" in evidence


def test_escalate_repo_pull(artifact):
    sha = "abc123abc123abc123abc123abc123abc123abc1"
    snap = artifact / "refs" / f"foo__bar@{sha[:12]}"
    (snap / "snapshot" / "src").mkdir(parents=True)
    (snap / "snapshot" / "src" / "config.py").write_text("QUALITY = 4.0\n")
    (snap / "provenance.json").write_text(json.dumps({"file_index": ["src/config.py"], "sha": sha}))
    (artifact / "references.json").write_text(json.dumps({"references": [{
        "kind": "github_repo", "status": "snapshotted",
        "detail": {"owner": "foo", "repo": "bar", "sha": sha,
                   "snapshot_dir": f"foo__bar@{sha[:12]}"}}]}))
    gaps = [{"where": "L1", "what_is_missing": "config",
             "likely_source": {"kind": "repo", "value": "src/config.py"}}]
    evidence, stats = rl.escalate(gaps, artifact, source_url="", max_frame_grabs=0)
    assert stats.repo_files == 1
    assert "QUALITY = 4.0" in evidence
    assert f"repo:src/config.py@{sha[:12]}" in evidence


def test_escalate_targeted_grab(artifact, monkeypatch):
    grabbed = {}

    def fake_grab(video, seconds, dest):
        grabbed["seconds"] = seconds
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"jpg")
        return dest

    class FakeOcr:
        text = "Final Gather Quality: 4.0"

    monkeypatch.setattr(rl, "_ensure_video", lambda out, url: "/fake/video.mp4")
    monkeypatch.setattr(rl, "_grab_frame", fake_grab)
    import frame_ocr
    monkeypatch.setattr(frame_ocr, "ocr_frame", lambda p: FakeOcr())

    gaps = [{"where": "L1", "what_is_missing": "value",
             "likely_source": {"kind": "timestamp", "value": "1:34:02"}}]
    evidence, stats = rl.escalate(gaps, artifact, source_url="https://x", max_frame_grabs=5)
    assert grabbed["seconds"] == 5642.0
    assert stats.frame_grabs == 1
    assert "Final Gather Quality: 4.0" in evidence
    assert "t=94:02" in evidence  # cited by timestamp


def test_escalate_respects_frame_budget(artifact, monkeypatch):
    monkeypatch.setattr(rl, "_ensure_video", lambda out, url: "/fake/video.mp4")
    monkeypatch.setattr(rl, "_grab_frame", lambda *a: pytest.fail("budget exceeded"))
    gaps = [{"where": "L1", "what_is_missing": "v",
             "likely_source": {"kind": "timestamp", "value": "0:10"}}]
    evidence, stats = rl.escalate(gaps, artifact, source_url="https://x", max_frame_grabs=0)
    assert stats.frame_grabs == 0
