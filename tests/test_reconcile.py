"""Unit tests for reconcile.py + the repo citation kind in citation.py."""
from __future__ import annotations

import json
from pathlib import Path

from yt_distill.core.citation import ResolutionContext, extract_citations, validate_citations
from yt_distill.stages.frame_ocr import FrameClass, FrameRecord
from yt_distill.core import reconcile as rc


# ---------------------------------------------------------------------------
# citation: repo kind
# ---------------------------------------------------------------------------

def test_extract_repo_citation_forms():
    text = ("see repo:src/main.py#L10-L40@abcdef1234567890abcdef1234567890abcdef12 "
            "and repo:README.md@abcdef1 done")
    repo_cits = [c for c in extract_citations(text) if c.kind == "repo"]
    assert [c.value for c in repo_cits] == [
        "src/main.py@abcdef1234567890abcdef1234567890abcdef12",
        "README.md@abcdef1",
    ]


def test_validate_repo_citation_short_sha_resolves():
    full_sha = "abcdef1234567890abcdef1234567890abcdef12"
    ctx = ResolutionContext(
        segment_ids=set(), frame_ids=set(), cluster_ids=set(),
        repo_refs={f"src/main.py@{full_sha}"})
    ok = validate_citations(f"repo:src/main.py#L1-L5@{full_sha[:12]}", ctx)
    assert ok.unresolved == []
    bad_path = validate_citations(f"repo:src/other.py@{full_sha[:12]}", ctx)
    assert len(bad_path.unresolved) == 1
    bad_sha = validate_citations("repo:src/main.py@deadbeef00", ctx)
    assert len(bad_sha.unresolved) == 1


def test_resolution_context_default_repo_refs_backcompat():
    ctx = ResolutionContext(segment_ids={0}, frame_ids=set(), cluster_ids=set())
    assert validate_citations("seg#0", ctx).unresolved == []


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------

CODE = (
    "def build_scene(quality):\n"
    "    lumen = Lumen(final_gather=quality)\n"
    "    scene = Scene(lumen)\n"
    "    scene.render()\n"
    "    return scene\n"
)

SHA = "1234567890abcdef1234567890abcdef12345678"


def _make_refs_tree(out_dir: Path, file_content: str) -> None:
    snap = out_dir / "refs" / f"foo__bar@{SHA[:12]}"
    (snap / "snapshot" / "src").mkdir(parents=True)
    (snap / "snapshot" / "src" / "scene.py").write_text(file_content)
    (snap / "provenance.json").write_text(json.dumps({
        "file_index": ["src/scene.py", "README.md"], "sha": SHA}))
    (out_dir / "references.json").write_text(json.dumps({
        "references": [{
            "url": "https://github.com/foo/bar", "kind": "github_repo",
            "status": "snapshotted",
            "detail": {"owner": "foo", "repo": "bar", "sha": SHA,
                       "clone_date": "2026-07-01T00:00:00Z",
                       "snapshot_dir": f"foo__bar@{SHA[:12]}"}}],
    }))


def _code_frame(cluster: str, text: str, ts: float = 65.0) -> FrameRecord:
    return FrameRecord(
        path=f"frames/frame_001_t-01-05.jpg", timestamp_seconds=ts,
        ocr_text=text, ocr_confidence=0.9, frame_class=FrameClass.CODE,
        class_confidence=0.9, cluster_id=cluster)


def test_reconcile_none_without_snapshots(tmp_path):
    assert rc.reconcile(tmp_path, frames=[_code_frame("c0", CODE)]) is None


def test_reconcile_match(tmp_path):
    _make_refs_tree(tmp_path, CODE)
    res = rc.reconcile(tmp_path, frames=[_code_frame("c0", CODE)])
    assert res is not None
    assert len(res.alignments) == 1
    a = res.alignments[0]
    assert (a.kind, a.path, a.cluster_id) == ("match", "src/scene.py", "c0")
    assert res.conflicts == []
    # repo_refs cover the whole file index, not just snapshotted files
    assert f"README.md@{SHA}" in res.repo_refs
    # evidence block is citable and bounded
    assert f"repo:src/scene.py@{SHA[:12]}" in res.evidence_markdown
    assert "MATCHES video" in res.evidence_markdown
    # audit artifact written
    audit = json.loads((tmp_path / "reconciliation.json").read_text())
    assert audit["alignments"][0]["kind"] == "match"


def test_reconcile_conflict_flagged_never_resolved(tmp_path):
    # Repo has a similar-but-different version (renamed var, changed value).
    repo_code = CODE.replace("quality", "final_quality").replace("scene.render()",
                                                                 "scene.render(hdr=True)")
    _make_refs_tree(tmp_path, repo_code)
    res = rc.reconcile(tmp_path, frames=[_code_frame("c0", CODE)],
                       video_upload_date="20260101")
    assert res is not None
    assert len(res.conflicts) == 1
    note = res.conflicts[0]["note"]
    assert "differs from repo:src/scene.py" in note
    assert "repo snapshot is newer than the video" in note
    assert "repo is authoritative for exact syntax" in note
    assert "CONFLICTS with video" in res.evidence_markdown
    # conflict is surfaced in evidence for the LLM to carry into the note
    assert res.conflicts[0]["note"] in res.evidence_markdown


def test_reconcile_unmatched_cluster(tmp_path):
    _make_refs_tree(tmp_path, CODE)
    unrelated = "SELECT * FROM completely_unrelated_table WHERE nothing;"
    res = rc.reconcile(tmp_path, frames=[_code_frame("c9", unrelated)])
    assert res is not None
    assert res.unmatched_clusters == ["c9"]
    assert res.alignments == []
