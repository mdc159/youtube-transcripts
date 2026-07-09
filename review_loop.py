"""Downstream-Hat Review Loop — the quality gate for skill bundles.

    uv run python review_loop.py <title-dir> [--max-iterations 3] \
        [--review-model X] [--synth-model Y] [--max-frame-grabs 12] [--dry-run]

Each iteration:
  1. A FRESH-context reviewer sees ONLY the bundle (SKILL.md + packaged refs +
     provenance — no transcript, no frames beyond those packaged, no memory of
     the distillation). It dry-runs every step and emits gaps wherever it would
     be guessing, as strict JSON.
  2. Gaps escalate deterministically against cached artifacts:
       timestamp → targeted ffmpeg frame grab (+OCR) at the flagged moment
       repo      → file pull from the pinned snapshot
       transcript→ keyword re-read with surrounding context
  3. A synthesizer revises only the affected sections with the new evidence.
  4. The bundle is rewritten (history preserved); the iteration is logged to
     the manifest's distill_runs and to provenance.

Loop ends when the reviewer reports no blocking gaps (status → complete) or
the iteration cap is hit (status → incomplete, residual gaps embedded in
provenance — never silently truncated).

Per-phase models: --review-model (cheap gap detection) / --synth-model (strong
re-synthesis); both default to the models.yaml default profile.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from citation import ResolutionContext, validate_citations
from enrichment import parse_formatted_transcript
from manifest import Manifest, MANIFEST_FILENAME
from models import resolve
from reconcile import load_snapshots
from skill_bundle import slugify, write_skill_bundle

MAX_REPO_FILE_LINES = 200
MAX_TRANSCRIPT_WINDOWS = 6
MAX_REPO_PULLS = 6


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Reviewer (fresh context, bundle only)
# ---------------------------------------------------------------------------

REVIEWER_PROMPT = """\
You are a fresh agent on a brand-new machine. You have been handed ONLY the
skill package below — no video, no transcript, no repository beyond the
packaged snapshot, and no memory of how the package was made. Your job is a
dry-run walkthrough: for each lesson step, narrate concretely how you would
execute it. Anywhere you would be GUESSING — a missing value, an ambiguous UI
location, an undefined term, code or an asset that is referenced but not
present — emit a gap.

Return STRICT JSON only (no prose, no code fences):
{
  "verdict": "pass" | "gaps",
  "blocking_gaps": [
    {"where": "<lesson/step or section>",
     "what_is_missing": "<one sentence>",
     "likely_source": {"kind": "timestamp" | "repo" | "transcript" | "unknown",
                        "value": "<H:MM:SS or MM:SS | path/in/repo | search keywords | ''>"}}
  ],
  "minor_gaps": [ same shape ]
}

A gap is BLOCKING when an agent cannot complete the step without the missing
information. Style nits, verbosity, and formatting are NOT gaps. If every step
is executable without guessing, return {"verdict": "pass", "blocking_gaps": [],
"minor_gaps": []}.
"""


def _bundle_text(bundle: Path) -> str:
    parts = [f"# SKILL.md\n\n{(bundle / 'SKILL.md').read_text()}"]
    prov = bundle / "provenance.json"
    if prov.is_file():
        parts.append(f"# provenance.json\n\n{prov.read_text()}")
    sources = bundle / "reference" / "sources.json"
    if sources.is_file():
        parts.append(f"# reference/sources.json\n\n{sources.read_text()}")
    assets = bundle / "assets"
    if assets.is_dir():
        names = "\n".join(f"- {p.name}" for p in sorted(assets.iterdir()))
        parts.append(f"# packaged assets\n\n{names}")
    ref = bundle / "reference"
    if ref.is_dir():
        listing = "\n".join(
            f"- {p.relative_to(ref)}" for p in sorted(ref.rglob("*")) if p.is_file())
        parts.append(f"# packaged reference files\n\n{listing}")
    return "\n\n---\n\n".join(parts)


def _parse_reviewer_json(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"reviewer returned no JSON object: {text[:200]!r}")
    data = json.loads(text[start:end + 1])
    data.setdefault("blocking_gaps", [])
    data.setdefault("minor_gaps", [])
    data.setdefault("verdict", "gaps" if data["blocking_gaps"] else "pass")
    return data


def _call_llm(profile, system: str, user: str) -> str:
    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"missing API key {profile.api_key_env}")
    client = OpenAI(base_url=profile.base_url, api_key=api_key)
    kwargs = dict(model=profile.model, messages=[
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    if profile.reasoning:
        kwargs["extra_body"] = {"reasoning": {"enabled": True}}
    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message.content or ""
    if not msg.strip():
        raise RuntimeError("provider returned empty content")
    return msg


# ---------------------------------------------------------------------------
# Escalation (deterministic, budget-capped)
# ---------------------------------------------------------------------------

def _parse_timestamp(value: str) -> float | None:
    value = value.strip().lstrip("t=").strip()
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", value)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"^(\d{1,4}):(\d{2})$", value)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        return float(value)
    except ValueError:
        return None


def _grab_frame(video_path: str, seconds: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seconds),
         "-i", video_path, "-frames:v", "1", "-q:v", "2", str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"ffmpeg grab at {seconds}s failed: {r.stderr.strip()[:200]}")
    return dest


def _ensure_video(out_dir: Path, source_url: str) -> str | None:
    """Reuse the media_cache video; re-download once if it was cleaned up."""
    cache_dir = Path("media_cache") / out_dir.name
    existing = sorted(cache_dir.glob("video.*")) if cache_dir.exists() else []
    if existing:
        return str(existing[0].resolve())
    if not source_url.startswith(("http://", "https://")):
        return source_url if Path(source_url).exists() else None
    cache_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["yt-dlp", "-f", "best[ext=mp4]", "-o", str(cache_dir / "video.%(ext)s"), source_url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[review] video re-download failed: {r.stderr.strip()[:200]}", file=sys.stderr)
        return None
    got = sorted(cache_dir.glob("video.*"))
    return str(got[0].resolve()) if got else None


@dataclass
class EscalationStats:
    frame_grabs: int = 0
    repo_files: int = 0
    transcript_windows: int = 0


def escalate(gaps: list[dict], out_dir: Path, *, source_url: str,
             max_frame_grabs: int) -> tuple[str, EscalationStats]:
    """Chase each gap's likely source. Returns (evidence markdown, stats)."""
    stats = EscalationStats()
    blocks: list[str] = []
    video_path: str | None = None
    segments = None
    snapshots = None

    for gap in gaps:
        src = gap.get("likely_source") or {}
        kind, value = src.get("kind", "unknown"), str(src.get("value") or "")
        where = gap.get("where", "?")

        if kind == "timestamp" and stats.frame_grabs < max_frame_grabs:
            seconds = _parse_timestamp(value)
            if seconds is None:
                continue
            if video_path is None:
                video_path = _ensure_video(out_dir, source_url)
            if video_path is None:
                blocks.append(f"## gap at {where}: video unavailable for targeted grab at {value}")
                continue
            try:
                dest = out_dir / "frames_targeted" / f"tgrab_{int(seconds):06d}.jpg"
                if not dest.is_file():
                    _grab_frame(video_path, seconds, dest)
                from frame_ocr import ocr_frame
                ocr = ocr_frame(str(dest))
                stats.frame_grabs += 1
                blocks.append(
                    f"## targeted frame at t={_fmt_ts(seconds)} (for gap at {where})\n"
                    f"On-screen text (OCR, cite as t={_fmt_ts(seconds)}):\n"
                    f"```\n{ocr.text.strip()[:2000]}\n```")
            except Exception as exc:  # noqa: BLE001 - per-gap isolation
                blocks.append(f"## gap at {where}: targeted grab failed ({exc})")

        elif kind == "repo" and stats.repo_files < MAX_REPO_PULLS:
            if snapshots is None:
                snapshots = load_snapshots(out_dir)
            for snap in snapshots or []:
                candidate = snap.snapshot_dir / "snapshot" / value
                if candidate.is_file():
                    lines = candidate.read_text(errors="replace").splitlines()
                    shown = "\n".join(
                        f"L{i + 1}: {l}" for i, l in enumerate(lines[:MAX_REPO_FILE_LINES]))
                    stats.repo_files += 1
                    blocks.append(
                        f"## repo:{value}@{snap.sha[:12]} (for gap at {where})\n"
                        f"```\n{shown}\n```")
                    break
            else:
                blocks.append(f"## gap at {where}: repo path {value!r} not in any snapshot")

        elif kind == "transcript" and stats.transcript_windows < MAX_TRANSCRIPT_WINDOWS:
            if segments is None:
                tpath = out_dir / f"{out_dir.name}_formatted_transcript.txt"
                segments = parse_formatted_transcript(tpath) if tpath.is_file() else []
            words = [w.lower() for w in re.findall(r"\w{4,}", value)][:6]
            if not words or not segments:
                continue
            hits = [s for s in segments if any(w in s.text.lower() for w in words)][:2]
            for seg in hits:
                lo = max(0, seg.seg_id - 2)
                hi = min(len(segments), seg.seg_id + 3)
                window = "\n".join(
                    f"seg#{s.seg_id} (t={_fmt_ts(s.start)}): {s.text}"
                    for s in segments[lo:hi])
                stats.transcript_windows += 1
                blocks.append(f"## transcript re-read (for gap at {where})\n{window}")

    return "\n\n".join(blocks), stats


# ---------------------------------------------------------------------------
# Re-synthesis
# ---------------------------------------------------------------------------

SYNTH_PROMPT = """\
You maintain a distilled skill document. A fresh-context reviewer dry-ran it
and found gaps; targeted evidence has been gathered for them. Revise the
document to close the gaps.

Rules:
- Revise ONLY what the gaps require; leave everything else byte-identical.
- Keep the existing section structure and citation discipline. New facts from
  targeted frames are cited by their timestamp (t=MM:SS); repo evidence as
  repo:path#Lx-Ly@SHA; transcript evidence as seg#NNN.
- Never invent values the evidence does not show. If the evidence still does
  not answer a gap, add it to the Open Gaps section instead.
- Every step keeps `status: distilled`.
- Return the COMPLETE revised markdown document, nothing else.
"""


def _synthesize(profile, current_md: str, gaps: list[dict], evidence: str) -> str:
    user = (
        f"# Current document\n\n{current_md}\n\n---\n\n"
        f"# Reviewer gaps\n\n{json.dumps(gaps, indent=2)}\n\n---\n\n"
        f"# Targeted evidence\n\n{evidence or '(no additional evidence could be gathered)'}"
    )
    return _call_llm(profile, SYNTH_PROMPT, user)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _resolve_out_dir(title_or_path: str) -> Path:
    p = Path(title_or_path)
    if p.is_absolute() and p.is_dir():
        return p
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    return (base / title_or_path).resolve()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Downstream-hat review loop over a skill bundle.")
    p.add_argument("title", help="Artifact dir name under Generated_Data, or absolute path")
    p.add_argument("--max-iterations", type=int, default=3)
    p.add_argument("--max-frame-grabs", type=int, default=12,
                   help="Targeted frame grabs per iteration (default 12)")
    p.add_argument("--review-model", default=None,
                   help="Model profile for gap detection (cheap; default models.yaml default)")
    p.add_argument("--synth-model", default=None,
                   help="Model profile for re-synthesis (strong; default models.yaml default)")
    p.add_argument("--dry-run", action="store_true",
                   help="Run reviewer once, print gaps, change nothing")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import env_bootstrap
    env_bootstrap.load()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    out_dir = _resolve_out_dir(args.title)
    repo_root = Path(__file__).resolve().parent

    manifest_path = out_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise RuntimeError(f"no {MANIFEST_FILENAME} in {out_dir}; run extract.py first")
    manifest = Manifest(out_dir, json.loads(manifest_path.read_text()))

    slug = slugify(manifest.data.get("title") or out_dir.name)
    bundle = out_dir / "skills" / slug
    if not (bundle / "SKILL.md").is_file():
        raise RuntimeError(f"no skill bundle at {bundle}; run distill.py <title> claude_skill first")

    review_profile = resolve(cli=args.review_model, models_yaml=repo_root / "models.yaml")
    synth_profile = resolve(cli=args.synth_model, models_yaml=repo_root / "models.yaml")
    print(f"[review] reviewer={review_profile.name} synthesizer={synth_profile.name}")

    provenance = json.loads((bundle / "provenance.json").read_text())
    history: list[dict] = provenance.get("review_iterations", [])
    source_url = manifest.data.get("source_url") or ""
    distill_result_path = next(iter(sorted(out_dir.glob("*_claude_skill.distill_result.json"))), None)
    distill_result = json.loads(distill_result_path.read_text()) if distill_result_path else {}

    final_status = "incomplete"
    residual_gaps: list[dict] = []

    for iteration in range(1, args.max_iterations + 1):
        print(f"[review] iteration {iteration}/{args.max_iterations}: reviewing bundle")
        review = _parse_reviewer_json(
            _call_llm(review_profile, REVIEWER_PROMPT, _bundle_text(bundle)))
        blocking = review["blocking_gaps"]
        print(f"[review] verdict={review['verdict']} "
              f"blocking={len(blocking)} minor={len(review['minor_gaps'])}")

        if args.dry_run:
            print(json.dumps(review, indent=2))
            return 0

        if not blocking:
            final_status = "complete"
            history.append({"iteration": iteration, "blocking_gaps": 0,
                            "minor_gaps": len(review["minor_gaps"]),
                            "escalations": {}, "resolved": True,
                            "reviewer_model": review_profile.name,
                            "completed_at": _utc_now()})
            residual_gaps = review["minor_gaps"]
            break

        evidence, stats = escalate(
            blocking, out_dir, source_url=source_url,
            max_frame_grabs=args.max_frame_grabs)
        print(f"[review] escalation: {stats.frame_grabs} frame grab(s), "
              f"{stats.repo_files} repo pull(s), {stats.transcript_windows} transcript window(s)")

        current_md = (bundle / "SKILL.md").read_text()
        # Strip our frontmatter before handing to the synthesizer; the bundle
        # writer re-attaches it deterministically.
        body = re.sub(r"\A---\n.*?\n---\n\n?", "", current_md, flags=re.DOTALL)
        revised = _synthesize(synth_profile, body, blocking, evidence)

        # Citation sanity on the revision (repo refs + timestamps validated).
        snapshots = load_snapshots(out_dir)
        tpath = out_dir / f"{out_dir.name}_formatted_transcript.txt"
        segs = parse_formatted_transcript(tpath) if tpath.is_file() else []
        from frame_ocr import read_ocr_json
        ocr_path = out_dir / "ocr.json"
        frames = read_ocr_json(ocr_path) if ocr_path.is_file() else []
        ctx = ResolutionContext(
            segment_ids={s.seg_id for s in segs},
            frame_ids={Path(f.path).stem for f in frames},
            cluster_ids={f.cluster_id for f in frames if f.cluster_id},
            repo_refs={f"{p}@{s.sha}" for s in snapshots for p in s.file_index},
        )
        val = validate_citations(revised, ctx)
        if val.unresolved:
            print(f"[review] WARNING: revision has {len(val.unresolved)} unresolved citations",
                  file=sys.stderr)

        history.append({"iteration": iteration, "blocking_gaps": len(blocking),
                        "minor_gaps": len(review["minor_gaps"]),
                        "escalations": stats.__dict__, "resolved": False,
                        "gaps": blocking,
                        "reviewer_model": review_profile.name,
                        "synth_model": synth_profile.name,
                        "unresolved_citations": [c.raw for c in val.unresolved],
                        "completed_at": _utc_now()})
        residual_gaps = blocking

        write_skill_bundle(
            out_dir, skill_md=revised, distill_result=distill_result,
            manifest_data=manifest.data,
            unresolved_citations=[c.raw for c in val.unresolved],
            review_iterations=history, status="distilled")
        print(f"[review] bundle re-synthesized ({len(revised)} chars)")

    else:
        # Cap hit with blocking gaps still open — ship marked incomplete.
        print(f"[review] iteration cap reached with {len(residual_gaps)} blocking gap(s); "
              f"shipping INCOMPLETE", file=sys.stderr)

    # Final provenance stamp (status + residual gaps + full history).
    provenance = json.loads((bundle / "provenance.json").read_text())
    provenance["status"] = final_status
    provenance["review_iterations"] = history
    provenance["residual_gaps"] = residual_gaps
    (bundle / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True))

    manifest.add_distill_run({
        "phase": "review_loop", "style": "claude_skill",
        "iterations": len(history), "status": final_status,
        "residual_gap_count": len(residual_gaps),
        "reviewer_model": review_profile.name, "synth_model": synth_profile.name,
    })
    manifest.save()

    print(f"[review] DONE: status={final_status} after {len(history)} iteration(s) → {bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
