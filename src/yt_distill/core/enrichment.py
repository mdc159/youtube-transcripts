"""Transcript enrichment: splice frame OCR/notes into the transcript at the
correct timestamp per the insertion rule (spec §4.6)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from yt_distill.stages.frame_ocr import FrameRecord, FrameClass


@dataclass
class TranscriptSegment:
    seg_id: int
    start: float
    end: float
    text: str


def parse_formatted_transcript(path: Path | str) -> list[TranscriptSegment]:
    """Parse `*_formatted_transcript.txt` (start|text per line). End = next start."""
    raw: list[tuple[float, str]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        ts_str, text = line.split("|", 1)
        try:
            raw.append((float(ts_str), text))
        except ValueError:
            continue
    segs: list[TranscriptSegment] = []
    for i, (ts, text) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else ts + 5.0
        segs.append(TranscriptSegment(seg_id=i, start=ts, end=end, text=text))
    return segs


def _fmt_ts(ts: float) -> str:
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"


def _frame_id(rec: FrameRecord) -> str:
    return Path(rec.path).stem  # e.g. frame_001_t-00-15


def _insertion_index(segs: list[TranscriptSegment], frame_ts: float) -> int:
    """Return the index AFTER which the frame should be inserted."""
    for i, s in enumerate(segs):
        if s.start <= frame_ts < s.end:
            return i
    # Not contained; find boundary
    for i, s in enumerate(segs):
        if s.end <= frame_ts and (i + 1 == len(segs) or segs[i + 1].start > frame_ts):
            return i
    return len(segs) - 1 if segs else 0


def enrich_transcript(segments: list[TranscriptSegment], frames: Iterable[FrameRecord]) -> str:
    """Build the enriched-transcript markdown string."""
    # Group frames by insertion index; only emit one block per code cluster.
    inserts: dict[int, list[str]] = {}
    seen_clusters: set[str] = set()
    for f in frames:
        idx = _insertion_index(segments, f.timestamp_seconds)
        block = _block_for(f, segments, seen_clusters)
        if block is None:
            continue
        inserts.setdefault(idx, []).append(block)

    lines: list[str] = []
    for i, seg in enumerate(segments):
        lines.append(f"[t={_fmt_ts(seg.start)}–{_fmt_ts(seg.end)} | seg#{seg.seg_id}] {seg.text}")
        for blk in inserts.get(i, []):
            lines.append("")
            lines.append(blk)
    return "\n".join(lines) + "\n"


def _block_for(f: FrameRecord, segments: list[TranscriptSegment], seen_clusters: set[str]) -> str | None:
    fid = _frame_id(f)
    has_low_conf = "~approximate" if f.ocr_confidence < 0.65 else ""
    if f.frame_class == FrameClass.CODE:
        # Only emit one block per cluster
        if f.cluster_id and f.cluster_id in seen_clusters:
            return None
        if f.cluster_id:
            seen_clusters.add(f.cluster_id)
        cluster_tag = f" [cluster_id={f.cluster_id}]" if f.cluster_id else ""
        marker = f" {has_low_conf}" if has_low_conf else ""
        return f"```code-from-{fid}{cluster_tag}{marker}\n{f.ocr_text.strip()}\n```"
    if f.frame_class == FrameClass.SLIDE_TEXT:
        marker = f" ({has_low_conf})" if has_low_conf else ""
        return f"> [slide t={_fmt_ts(f.timestamp_seconds)} | {fid}{marker}] {f.ocr_text.strip()}"
    if f.frame_class == FrameClass.UI:
        return f"_[ui {fid}]_ {f.ocr_text.strip()}"
    if f.frame_class == FrameClass.DIAGRAM:
        return f"_[diagram {fid}]_ (see vision payload)"
    return None  # OTHER class: no inline injection


def write_enriched_transcript(path: Path | str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")
