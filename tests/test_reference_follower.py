"""Unit tests for reference_follower.py (harvest / classify / snapshot / orchestrate)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from yt_distill.stages import references as rf
from yt_distill.core.manifest import Manifest


# ---------------------------------------------------------------------------
# harvest_urls
# ---------------------------------------------------------------------------

def test_harvest_strips_trailing_punctuation():
    text = "see https://github.com/foo/bar. and https://example.com/x, done"
    assert rf.harvest_urls(text) == [
        "https://github.com/foo/bar",
        "https://example.com/x",
    ]


def test_harvest_markdown_paren_wrapper():
    text = "[repo](https://github.com/foo/bar) and (https://example.com/y)"
    assert rf.harvest_urls(text) == [
        "https://github.com/foo/bar",
        "https://example.com/y",
    ]


def test_harvest_empty_and_no_urls():
    assert rf.harvest_urls("") == []
    assert rf.harvest_urls("no links here") == []


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------

def test_normalize_strips_tracking_and_fragment():
    url = "https://YouTu.be/abc?si=XYZ&t=42#frag"
    assert rf.normalize_url(url) == "https://youtu.be/abc?t=42"


def test_normalize_dedups_trailing_slash():
    assert rf.normalize_url("https://github.com/a/b/") == rf.normalize_url("https://github.com/a/b")


# ---------------------------------------------------------------------------
# classify_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url,kind",
    [
        ("https://github.com/foo/bar", "github_repo"),
        ("https://github.com/foo/bar/blob/main/src/x.py", "github_repo"),
        ("https://github.com/foo", "other"),
        ("https://gist.github.com/foo/123", "docs"),
        ("https://docs.unrealengine.com/5.3/en-US/lumen", "docs"),
        ("https://dev.epicgames.com/documentation/en-us/unreal-engine", "docs"),
        ("https://example.com/manual/setup", "docs"),
        ("https://drive.google.com/file/d/abc", "asset_download"),
        ("https://example.com/pack.zip", "asset_download"),
        ("https://polyhaven.com/a/studio_small_03", "asset_download"),
        ("https://twitter.com/someone", "other"),
    ],
)
def test_classify(url, kind):
    assert rf.classify_url(url) == kind


def test_parse_github_repo_deep_link():
    owner, repo, referenced = rf.parse_github_repo(
        "https://github.com/foo/bar/blob/main/src/thing.py")
    assert (owner, repo, referenced) == ("foo", "bar", "src/thing.py")


def test_parse_github_repo_git_suffix():
    owner, repo, referenced = rf.parse_github_repo("https://github.com/foo/bar.git")
    assert (owner, repo, referenced) == ("foo", "bar", None)


# ---------------------------------------------------------------------------
# collect_candidates provenance
# ---------------------------------------------------------------------------

def _make_artifact_dir(tmp_path: Path, title: str = "Test") -> Path:
    out_dir = tmp_path / title
    out_dir.mkdir(parents=True)
    (out_dir / f"{title}_formatted_transcript.txt").write_text(
        "0.0|intro no links\n5.0|grab the repo at https://github.com/foo/bar today\n")
    (out_dir / f"{title}_clean_text.txt").write_text(
        "intro no links grab the repo at https://github.com/foo/bar today main.py")
    return out_dir


def test_collect_candidates_provenance(tmp_path):
    out_dir = _make_artifact_dir(tmp_path)
    meta = {
        "description": "download assets: https://example.com/pack.zip",
        "comments": [
            {"text": "pinned: https://github.com/foo/bar", "is_pinned": True,
             "author_is_uploader": True},
        ],
    }
    cands = rf.collect_candidates(out_dir, meta)
    by_kind = {r["kind"] for r in cands.values()}
    assert by_kind == {"github_repo", "asset_download"}
    repo = next(r for r in cands.values() if r["kind"] == "github_repo")
    wheres = {f["where"] for f in repo["found_in"]}
    assert "pinned_comment" in wheres
    assert "seg#1" in wheres


# ---------------------------------------------------------------------------
# snapshot_repo (local file:// clone, no network)
# ---------------------------------------------------------------------------

@pytest.fixture()
def local_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    repo = tmp_path / "upstream"
    repo.mkdir()
    (repo / "README.md").write_text("# upstream\n")
    (repo / "package.json").write_text("{}")
    src = repo / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hi')\n")
    (src / "unrelated.py").write_text("pass\n")
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


def test_snapshot_repo_selects_and_pins(tmp_path, local_repo, monkeypatch):
    # Point the clone at the local upstream instead of github.
    monkeypatch.setattr(
        rf, "parse_github_repo", lambda url: ("foo", "bar", None))
    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        if cmd[:2] == ["git", "clone"]:
            cmd = [*cmd[:-2], f"file://{local_repo}", cmd[-1]]
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(rf.subprocess, "run", fake_run)

    dest = tmp_path / "refs"
    detail = rf.snapshot_repo(
        "https://github.com/foo/bar", dest,
        max_repo_mb=50, tutorial_tokens={"main.py"})

    assert len(detail["sha"]) == 40
    whys = {f["path"]: f["why"] for f in detail["files_snapshotted"]}
    assert whys["README.md"] == "build_setup"
    assert whys["package.json"] == "build_setup"
    assert whys["src/main.py"] == "referenced_in_tutorial"
    assert "src/unrelated.py" not in whys

    snap = dest / detail["snapshot_dir"]
    assert (snap / "snapshot" / "README.md").exists()
    assert (snap / "snapshot" / "src" / "main.py").exists()
    prov = json.loads((snap / "provenance.json").read_text())
    assert prov["sha"] == detail["sha"]
    assert "src/unrelated.py" in prov["file_index"]


def test_snapshot_repo_size_cap(tmp_path, local_repo, monkeypatch):
    monkeypatch.setattr(rf, "parse_github_repo", lambda url: ("foo", "bar", None))
    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        if cmd[:2] == ["git", "clone"]:
            cmd = [*cmd[:-2], f"file://{local_repo}", cmd[-1]]
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(rf.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="max-repo-mb"):
        rf.snapshot_repo("https://github.com/foo/bar", tmp_path / "refs",
                         max_repo_mb=0, tutorial_tokens=set())


# ---------------------------------------------------------------------------
# main() orchestration
# ---------------------------------------------------------------------------

def _seed_manifest(out_dir: Path) -> None:
    m = Manifest.load_or_create(
        out_dir, source_id="yt:test123abcd", source_url="https://youtu.be/test123abcd",
        title=out_dir.name, duration_seconds=10.0)
    m.save()


def test_main_records_and_is_idempotent(tmp_path, monkeypatch):
    out_dir = _make_artifact_dir(tmp_path)
    _seed_manifest(out_dir)

    # No network: canned source meta; no snapshot/doc fetch side effects needed
    monkeypatch.setattr(
        rf, "_fetch_source_meta",
        lambda *a, **k: {"fetched_at": "2026-01-01T00:00:00Z", "description": "",
                         "upload_date": None, "channel": None, "comments": []})
    monkeypatch.setattr(
        rf, "snapshot_repo",
        lambda url, root, **k: {"owner": "foo", "repo": "bar", "sha": "0" * 40,
                                "clone_date": "2026-01-01T00:00:00Z",
                                "snapshot_dir": "foo__bar@000000000000",
                                "files_snapshotted": [], "size_bytes": 1,
                                "clone_url": "https://github.com/foo/bar.git",
                                "file_index_count": 0})

    rc = rf.main([str(out_dir)])
    assert rc == 0

    refs = json.loads((out_dir / "references.json").read_text())
    assert refs["schema_version"] == 1
    assert len(refs["references"]) == 1
    assert refs["references"][0]["status"] == "snapshotted"

    manifest = json.loads((out_dir / "artifact_manifest.json").read_text())
    assert manifest["references"]["reference_count"] == 1
    assert manifest["references"]["files"]["references_json"]["path"] == "references.json"

    # Second run skips (idempotent) — poison the fetchers to prove no work is done.
    monkeypatch.setattr(rf, "collect_candidates",
                        lambda *a, **k: pytest.fail("should have skipped"))
    assert rf.main([str(out_dir)]) == 0


def test_main_requires_manifest(tmp_path):
    out_dir = tmp_path / "NoManifest"
    out_dir.mkdir()
    with pytest.raises(RuntimeError, match="run extract.py first"):
        rf.main([str(out_dir)])


def test_main_max_fetches_zero_skips_network(tmp_path, monkeypatch):
    out_dir = _make_artifact_dir(tmp_path)
    _seed_manifest(out_dir)
    monkeypatch.setattr(
        rf, "_fetch_source_meta",
        lambda *a, **k: {"fetched_at": "2026-01-01T00:00:00Z", "description": "",
                         "upload_date": None, "channel": None, "comments": []})
    monkeypatch.setattr(rf, "snapshot_repo",
                        lambda *a, **k: pytest.fail("must not clone at max_fetches=0"))
    rc = rf.main([str(out_dir), "--max-fetches", "0"])
    assert rc == 0
    refs = json.loads((out_dir / "references.json").read_text())
    assert refs["references"][0]["status"] == "skipped"


def test_shortlink_resolution_reclassifies(tmp_path, monkeypatch):
    out_dir = tmp_path / "Short"
    out_dir.mkdir()
    (out_dir / "Short_formatted_transcript.txt").write_text("0.0|no links\n")
    (out_dir / "Short_clean_text.txt").write_text("no links")
    _seed = Manifest.load_or_create(
        out_dir, source_id="yt:short123456", source_url="https://youtu.be/short123456",
        title="Short", duration_seconds=1.0)
    _seed.save()
    monkeypatch.setattr(
        rf, "_fetch_source_meta",
        lambda *a, **k: {"fetched_at": "2026-01-01T00:00:00Z",
                         "description": "assets: https://bit.ly/abc123",
                         "upload_date": None, "channel": None, "comments": []})
    monkeypatch.setattr(rf, "resolve_shortlink",
                        lambda url: "https://example.com/assets/pack.zip")
    rc = rf.main([str(out_dir), "--max-fetches", "0"])
    assert rc == 0
    refs = json.loads((out_dir / "references.json").read_text())
    rec = refs["references"][0]
    assert rec["kind"] == "asset_download"
    assert rec["resolved_url"] == "https://example.com/assets/pack.zip"
