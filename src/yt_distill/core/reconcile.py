"""Reconciliation pass: cross-check transcript, OCR code clusters, and pinned
repo snapshots (spec: Lesson Liberation §2).

Evidence authority:
  - repo code       → exact syntax
  - transcript      → intent, ordering, rationale
  - OCR clusters    → the bridge (which repo file is on screen at which time)

Conflicts are FLAGGED, never silently resolved. Output feeds two consumers:
  - `reconciliation.json` under the artifact dir (audit / downstream review)
  - a Repo Evidence markdown block injected into the distill payload, giving
    the LLM citable `repo:path#Lx-Ly@SHA` material and the known conflicts.

Deterministic — no LLM calls here. Alignment uses the same rapidfuzz matching
family as frame dedup.
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from yt_distill.stages.frame_ocr import FrameClass, FrameRecord

RECONCILIATION_FILENAME = "reconciliation.json"
SCHEMA_VERSION = 1

# File-finding threshold (token_set_ratio, 0-100): below this, no repo
# counterpart is claimed at all. token_set_ratio is deliberately forgiving —
# robust to OCR noise and reordering — so it locates the right file.
CONFLICT_THRESHOLD = 55.0
# Match-vs-conflict classification uses the stricter, order-sensitive
# fuzz.ratio on the best window: renames, changed values, and added lines
# push it down where token_set_ratio would shrug. Calibration: clean-screen
# OCR of identical code stays ≥95; a small rename on a short snippet lands
# ~91. We flag the gray zone as conflict on purpose — the contract requires
# conflicts to be surfaced, never silently resolved, so over-flagging is the
# safer failure mode.
STRICT_MATCH_THRESHOLD = 93.0

# Evidence budget: keep the payload addition bounded.
MAX_EVIDENCE_FILES = 8
MAX_EVIDENCE_LINES_PER_FILE = 250
MAX_SNAPSHOT_FILE_BYTES = 200_000


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(text: str) -> str:
    """Comment-stripped, whitespace-collapsed (mirrors frame_ocr dedup prep)."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"(#|//).*$", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _fmt_ts(ts: float) -> str:
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"


@dataclass
class RepoSnapshot:
    owner: str
    repo: str
    sha: str
    clone_date: str | None
    snapshot_dir: Path            # refs/<owner>__<repo>@<sha12>/
    file_index: list[str]         # every file in the repo at the pinned SHA


@dataclass
class Alignment:
    cluster_id: str
    timestamp_seconds: float
    repo: str                     # owner/repo
    sha: str
    path: str
    line_start: int
    line_end: int
    score: float
    kind: str                     # match | conflict


@dataclass
class ReconcileResult:
    repos: list[RepoSnapshot]
    alignments: list[Alignment]
    conflicts: list[dict]
    unmatched_clusters: list[str]
    repo_refs: set[str] = field(default_factory=set)
    evidence_markdown: str = ""


def load_snapshots(out_dir: Path) -> list[RepoSnapshot]:
    """Pinned repo snapshots recorded by reference_follower."""
    refs_path = out_dir / "references.json"
    if not refs_path.is_file():
        return []
    data = json.loads(refs_path.read_text(encoding="utf-8"))
    snaps: list[RepoSnapshot] = []
    for rec in data.get("references", []):
        if rec.get("kind") != "github_repo" or rec.get("status") != "snapshotted":
            continue
        detail = rec.get("detail") or {}
        snap_dir = out_dir / "refs" / detail.get("snapshot_dir", "")
        prov_path = snap_dir / "provenance.json"
        file_index: list[str] = []
        if prov_path.is_file():
            file_index = json.loads(prov_path.read_text(encoding="utf-8")).get("file_index", [])
        snaps.append(RepoSnapshot(
            owner=detail.get("owner", ""),
            repo=detail.get("repo", ""),
            sha=detail.get("sha", ""),
            clone_date=detail.get("clone_date"),
            snapshot_dir=snap_dir,
            file_index=file_index,
        ))
    return snaps


def _snapshot_files(snap: RepoSnapshot) -> dict[str, list[str]]:
    """path → lines, for every text file physically present in the snapshot."""
    root = snap.snapshot_dir / "snapshot"
    out: dict[str, list[str]] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or p.stat().st_size > MAX_SNAPSHOT_FILE_BYTES:
            continue
        try:
            text = p.read_text(errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        out[p.relative_to(root).as_posix()] = text.splitlines()
    return out


def _cluster_representatives(frames: list[FrameRecord]) -> dict[str, FrameRecord]:
    """One representative frame per code cluster (highest OCR confidence)."""
    reps: dict[str, FrameRecord] = {}
    for f in frames:
        if f.frame_class != FrameClass.CODE or not f.cluster_id:
            continue
        cur = reps.get(f.cluster_id)
        if cur is None or f.ocr_confidence > cur.ocr_confidence:
            reps[f.cluster_id] = f
    return reps


def _best_window(cluster_norm: str, file_lines: list[str], window: int) -> tuple[float, int, int]:
    """Best-scoring window of `window` lines in the file. Returns (score, start, end) 1-based."""
    if not file_lines:
        return 0.0, 1, 1
    window = max(3, min(window, len(file_lines)))
    step = max(1, window // 2)
    best = (0.0, 1, min(window, len(file_lines)))
    for start in range(0, len(file_lines), step):
        chunk = file_lines[start:start + window]
        if not chunk:
            break
        score = fuzz.token_set_ratio(cluster_norm, _normalize("\n".join(chunk)))
        if score > best[0]:
            best = (score, start + 1, start + len(chunk))
        if start + window >= len(file_lines):
            break
    return best


def reconcile(out_dir: Path, *, frames: list[FrameRecord],
              video_upload_date: str | None = None) -> ReconcileResult | None:
    """Run the pass. Returns None when there is no pinned repo evidence."""
    out_dir = Path(out_dir)
    snaps = load_snapshots(out_dir)
    if not snaps:
        return None

    reps = _cluster_representatives(frames)
    alignments: list[Alignment] = []
    conflicts: list[dict] = []
    unmatched: list[str] = []

    per_snap_files = [(s, _snapshot_files(s)) for s in snaps]

    for cluster_id, rep in sorted(reps.items()):
        cluster_norm = _normalize(rep.ocr_text)
        if not cluster_norm:
            unmatched.append(cluster_id)
            continue
        n_lines = max(3, len(cluster_norm.splitlines()))
        best: tuple[float, RepoSnapshot, str, int, int, list[str]] | None = None
        for snap, files in per_snap_files:
            for path, lines in files.items():
                score, ls, le = _best_window(cluster_norm, lines, n_lines * 2)
                if best is None or score > best[0]:
                    best = (score, snap, path, ls, le, lines)
        if best is None or best[0] < CONFLICT_THRESHOLD:
            unmatched.append(cluster_id)
            continue
        score, snap, path, ls, le, file_lines = best
        window_norm = _normalize("\n".join(file_lines[ls - 1:le]))
        strict = fuzz.ratio(cluster_norm, window_norm)
        kind = "match" if strict >= STRICT_MATCH_THRESHOLD else "conflict"
        score = round(min(score, strict), 1)
        alignments.append(Alignment(
            cluster_id=cluster_id,
            timestamp_seconds=rep.timestamp_seconds,
            repo=f"{snap.owner}/{snap.repo}",
            sha=snap.sha,
            path=path,
            line_start=ls,
            line_end=le,
            score=round(score, 1),
            kind=kind,
        ))
        if kind == "conflict":
            newer = "repo snapshot is newer than the video" if (
                video_upload_date and snap.clone_date
                and snap.clone_date[:10].replace("-", "") > video_upload_date
            ) else "recency unknown"
            conflicts.append({
                "cluster_id": cluster_id,
                "timestamp": f"t={_fmt_ts(rep.timestamp_seconds)}",
                "repo_ref": f"repo:{path}#L{ls}-L{le}@{snap.sha[:12]}",
                "similarity": round(score, 1),
                "note": (
                    f"video shows code at t={_fmt_ts(rep.timestamp_seconds)} "
                    f"(cluster_id={cluster_id}) that differs from repo:{path}@{snap.sha[:12]} "
                    f"(similarity {score:.0f}); {newer}; repo is authoritative for exact syntax"
                ),
            })

    repo_refs = {f"{p}@{s.sha}" for s in snaps for p in s.file_index}
    result = ReconcileResult(
        repos=snaps,
        alignments=alignments,
        conflicts=conflicts,
        unmatched_clusters=unmatched,
        repo_refs=repo_refs,
    )
    result.evidence_markdown = _build_evidence_markdown(result, per_snap_files)
    _write_reconciliation_json(out_dir, result)
    return result


def _build_evidence_markdown(result: ReconcileResult,
                             per_snap_files: list[tuple[RepoSnapshot, dict[str, list[str]]]]) -> str:
    lines: list[str] = ["", "---", "", "# Repo Evidence (citable as `repo:path#Lx-Ly@SHA`)", ""]
    for snap in result.repos:
        lines.append(f"- pinned repository `{snap.owner}/{snap.repo}` @ `{snap.sha}` "
                     f"(cloned {snap.clone_date}; {len(snap.file_index)} files in index)")
    files_by_key = {(s.owner + "/" + s.repo, path): (s, fl)
                    for s, files in per_snap_files for path, fl in files.items()}

    # Evidence files: those an alignment points at, best score first, capped.
    seen: set[tuple[str, str]] = set()
    picked: list[Alignment] = []
    for a in sorted(result.alignments, key=lambda a: -a.score):
        key = (a.repo, a.path)
        if key in seen or key not in files_by_key:
            continue
        seen.add(key)
        picked.append(a)
        if len(picked) >= MAX_EVIDENCE_FILES:
            break

    for a in picked:
        snap, file_lines = files_by_key[(a.repo, a.path)]
        lo = max(0, a.line_start - 1 - 10)
        hi = min(len(file_lines), a.line_end + 10)
        shown = file_lines[lo:hi][:MAX_EVIDENCE_LINES_PER_FILE]
        lines.append("")
        lines.append(f"## repo:{a.path}@{snap.sha[:12]} "
                     f"(on screen at t={_fmt_ts(a.timestamp_seconds)}, cluster_id={a.cluster_id}, "
                     f"{'MATCHES video' if a.kind == 'match' else 'CONFLICTS with video'})")
        lines.append("```")
        lines.extend(f"L{lo + i + 1}: {l}" for i, l in enumerate(shown))
        lines.append("```")

    if result.conflicts:
        lines.append("")
        lines.append("## Reconciliation conflicts (carry each relevant one into the note; never resolve silently)")
        for c in result.conflicts:
            lines.append(f"- {c['note']}")
    if result.unmatched_clusters:
        lines.append("")
        lines.append(f"_Unmatched code clusters (no repo counterpart found): "
                     f"{', '.join(result.unmatched_clusters)}_")
    lines.append("")
    return "\n".join(lines)


def _write_reconciliation_json(out_dir: Path, result: ReconcileResult) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "repos": [{"repo": f"{s.owner}/{s.repo}", "sha": s.sha,
                   "clone_date": s.clone_date, "file_index_count": len(s.file_index)}
                  for s in result.repos],
        "alignments": [a.__dict__ for a in result.alignments],
        "conflicts": result.conflicts,
        "unmatched_clusters": result.unmatched_clusters,
    }
    (out_dir / RECONCILIATION_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
