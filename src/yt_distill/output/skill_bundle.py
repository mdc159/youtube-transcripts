"""Emit a self-sufficient skill package from a claude_skill distill run.

Consumes the distilled markdown + artifact tree and writes:

    Generated_Data/<title>/skills/<slug>/
      SKILL.md          # frontmatter (name, trigger description) + distilled body
      assets/           # frames the note actually cites (load-bearing evidence)
      reference/        # repo pointers (URL + SHA), doc snapshots, repo snapshots
      provenance.json   # source URL, video date, tiers used, review iterations,
                        # unresolved gaps — enough to detect staleness later

The consuming agent gets ONLY this directory; everything it needs must be
inside. Deterministic — no LLM calls here.
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path

from yt_distill.core.citation import extract_citations

BUNDLE_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60].rstrip("-") or "skill"


def _extract_trigger_description(skill_md: str) -> str:
    """First paragraph under '### 1. When To Use This Skill' (or any heading
    containing 'when to use'); falls back to the first non-heading paragraph."""
    lines = skill_md.splitlines()
    in_section = False
    para: list[str] = []
    for line in lines:
        if re.match(r"^#{2,4}\s", line):
            if in_section and para:
                break
            in_section = "when to use" in line.lower()
            continue
        if in_section:
            if line.strip():
                para.append(line.strip())
            elif para:
                break
    if not para:
        for line in lines:
            s = line.strip()
            if s and not s.startswith(("#", "|", "-", ">", "```")):
                para.append(s)
                break
    return " ".join(para)[:500] or "Distilled lesson skill."


def _frontmatter(name: str, description: str) -> str:
    desc = description.replace('"', "'")
    return f'---\nname: {name}\ndescription: "{desc}"\n---\n\n'


def _cited_frame_files(skill_md: str, out_dir: Path) -> list[Path]:
    """Frames the note actually cites — the load-bearing visual evidence."""
    frames_dir = out_dir / "frames"
    if not frames_dir.is_dir():
        return []
    by_stem = {p.stem: p for p in frames_dir.iterdir() if p.is_file()}
    picked: dict[str, Path] = {}
    for cit in extract_citations(skill_md):
        if cit.kind != "frame":
            continue
        if cit.value in by_stem:
            picked[cit.value] = by_stem[cit.value]
        else:  # short form frame_NNN
            for stem, p in by_stem.items():
                if stem.startswith(cit.value + "_"):
                    picked[stem] = p
                    break
    return [picked[k] for k in sorted(picked)]


def _load_references(out_dir: Path) -> dict:
    path = out_dir / "references.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def write_skill_bundle(
    out_dir: Path,
    *,
    skill_md: str,
    distill_result: dict,
    manifest_data: dict,
    unresolved_citations: list[str] | None = None,
    review_iterations: list[dict] | None = None,
    status: str = "distilled",
) -> Path:
    """Write the bundle; returns the bundle directory. Overwrites prior bundle
    for the same slug (a re-distill supersedes it)."""
    out_dir = Path(out_dir)
    title = manifest_data.get("title") or out_dir.name
    slug = slugify(title)
    bundle = out_dir / "skills" / slug
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    # SKILL.md — deterministic frontmatter over the distilled body.
    description = _extract_trigger_description(skill_md)
    (bundle / "SKILL.md").write_text(_frontmatter(slug, description) + skill_md.strip() + "\n", encoding="utf-8")

    # assets/ — only frames the note cites.
    cited = _cited_frame_files(skill_md, out_dir)
    if cited:
        assets = bundle / "assets"
        assets.mkdir()
        for src in cited:
            shutil.copy2(src, assets / src.name)

    # reference/ — repo pointers + packaged snapshots + aux docs.
    references = _load_references(out_dir)
    ref_entries = references.get("references", [])
    repo_pointers = []
    ref_dir = bundle / "reference"
    for rec in ref_entries:
        detail = rec.get("detail") or {}
        if rec.get("kind") == "github_repo" and rec.get("status") == "snapshotted":
            repo_pointers.append({
                "url": rec.get("url"),
                "clone_url": detail.get("clone_url"),
                "sha": detail.get("sha"),
                "clone_date": detail.get("clone_date"),
            })
            snap = out_dir / "refs" / detail.get("snapshot_dir", "")
            if detail.get("snapshot_dir") and snap.is_dir():
                ref_dir.mkdir(exist_ok=True)
                shutil.copytree(snap, ref_dir / snap.name, dirs_exist_ok=True)
        elif rec.get("kind") == "docs" and rec.get("status") == "fetched":
            doc_rel = detail.get("path")
            doc_src = out_dir / doc_rel if doc_rel else None
            if doc_src and doc_src.is_file():
                dest = ref_dir / "docs" / doc_src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(doc_src, dest)
    if repo_pointers or ref_entries:
        ref_dir.mkdir(exist_ok=True)
        (ref_dir / "sources.json").write_text(json.dumps({
            "repo_pointers": repo_pointers,
            "all_references": [
                {k: r.get(k) for k in ("url", "kind", "status")} for r in ref_entries
            ],
        }, indent=2, sort_keys=True), encoding="utf-8")

    # provenance.json — staleness detection + downstream audit trail.
    source_meta_path = out_dir / "refs" / "source_meta.json"
    source_meta = json.loads(source_meta_path.read_text(encoding="utf-8")) if source_meta_path.is_file() else {}
    provenance = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_id": manifest_data.get("source_id"),
        "source_url": manifest_data.get("source_url"),
        "video_title": title,
        "video_duration_seconds": manifest_data.get("duration_seconds"),
        "video_upload_date": source_meta.get("upload_date"),
        "distilled_at": _utc_now(),
        "model_profile": distill_result.get("model_profile"),
        "prompt_contract_version": distill_result.get("prompt_contract_version"),
        "transcript_source": (manifest_data.get("extract") or {}).get("transcript_source"),
        "transcript_quality": (manifest_data.get("extract") or {}).get("transcript_quality"),
        "quality": distill_result.get("quality"),
        "repo_pointers": repo_pointers,
        "review_iterations": list(review_iterations or []),  # appended by the review loop
        "status": status,              # distilled → complete | incomplete (review loop)
        "unresolved_gaps": list(unresolved_citations or []),
        "assets_packaged": [p.name for p in cited],
    }
    (bundle / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")

    return bundle
