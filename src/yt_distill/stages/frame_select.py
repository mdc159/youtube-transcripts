"""Scene-change-aware frame selection (spec §4.4).

Primary: perceptual-hash deltas between consecutive frames; pick frames just
after each change point. Fallback: even spacing across remaining gaps.
Token-budget aware: final count = min(--max-vision-frames, budget // est).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import imagehash
from PIL import Image


@dataclass
class ChangePoint:
    index: int
    distance: int  # Hamming distance from previous frame's phash


def _phash(path: Path | str) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return imagehash.phash(img)


def detect_scene_changes(paths: Sequence[Path | str], threshold_factor: float = 1.5) -> list[ChangePoint]:
    """Return change points where Hamming distance > median + threshold_factor*MAD.

    For very short sequences (<3 frames) we cannot compute a stable threshold;
    return an empty list.
    """
    if len(paths) < 2:
        return []
    hashes = [_phash(p) for p in paths]
    distances = [hashes[i] - hashes[i - 1] for i in range(1, len(hashes))]
    if len(distances) < 3:
        # Short sequences: any non-zero delta is a change.
        return [ChangePoint(index=i + 1, distance=d) for i, d in enumerate(distances) if d > 0]
    median = statistics.median(distances)
    mad = statistics.median([abs(d - median) for d in distances])
    if mad == 0:
        # Degenerate distribution (most distances identical): any deviation
        # above the median is a change.
        threshold = median
    else:
        threshold = median + threshold_factor * mad
    return [ChangePoint(index=i + 1, distance=d) for i, d in enumerate(distances) if d > threshold]


from yt_distill.stages.frame_ocr import FrameRecord, FrameClass  # noqa: E402  (after class def)


@dataclass
class Selected:
    path: str
    timestamp_seconds: float
    frame_class: FrameClass
    reason: str  # e.g. "scene_change@t=01:23" or "even_spacing@t=03:45"


@dataclass
class SelectionResult:
    selected: list[Selected]


def _fmt_t(ts: float) -> str:
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"


def select_frames(
    frames: list[FrameRecord],
    *,
    change_points: list[ChangePoint],
    max_frames: int,
    token_budget: int | None,
    est_image_tokens: int = 5000,
    style: str = "knowledge_base",
) -> SelectionResult:
    """Select frames for the vision payload.

    Order of operations (spec §4.4):
      1. Filter or prioritize frames by style.
      2. Take frames just after each change_point index.
      3. Fill remaining budget with even-spacing across the surviving frames.
      4. Cap by min(max_frames, token_budget // est_image_tokens) if budget given.
    """
    eligible_pairs: list[tuple[int, FrameRecord]] = []
    for orig_idx, frame in enumerate(frames):
        if _include_for_style(frame, style):
            eligible_pairs.append((orig_idx, frame))
    eligible_pairs = _order_for_style(eligible_pairs, style)

    eligible: list[FrameRecord] = []
    original_to_eligible: dict[int, int] = {}
    for orig_idx, f in eligible_pairs:
        original_to_eligible[orig_idx] = len(eligible)
        eligible.append(f)
    if not eligible:
        return SelectionResult(selected=[])

    cap = max_frames
    if token_budget is not None:
        cap = min(cap, max(0, token_budget // max(1, est_image_tokens)))
    if cap == 0:
        return SelectionResult(selected=[])

    # Index `change_points` are positions in the *original* `frames` list.
    chosen_idx: list[tuple[int, str]] = []  # (index in eligible, reason)
    for cp in change_points:
        if cp.index in original_to_eligible:
            idx = original_to_eligible[cp.index]
            f = eligible[idx]
            if not any(i == idx for i, _ in chosen_idx):
                chosen_idx.append((idx, f"scene_change@t={_fmt_t(f.timestamp_seconds)}"))
                if len(chosen_idx) >= cap:
                    break

    if len(chosen_idx) < cap:
        already = {i for i, _ in chosen_idx}
        n = len(eligible)
        if n > 0:
            # First pass: anchored even spacing across [0, n-1]. With remaining=k
            # slots, we ideally want indices i*(n-1)/(k-1) for i in 0..k-1. Use
            # this as the preferred order; skip already-chosen indices.
            remaining = cap - len(chosen_idx)
            if remaining >= n:
                # Fewer than `remaining` eligible — just take everything not yet chosen.
                preferred = list(range(n))
            elif style == "diy_project":
                preferred = list(range(n))
            elif remaining == 1:
                preferred = [n // 2]  # midpoint when only one slot
            else:
                preferred = sorted({(i * (n - 1)) // (remaining - 1) for i in range(remaining)})

            # Second pass: walk preferred, then fill any gaps from remaining indices.
            for i in preferred:
                if i in already:
                    continue
                f = eligible[i]
                chosen_idx.append((i, f"even_spacing@t={_fmt_t(f.timestamp_seconds)}"))
                already.add(i)
                if len(chosen_idx) >= cap:
                    break

            # If we still haven't reached cap (because preferred collided with
            # already-chosen indices), walk all indices in order and grab the
            # next un-chosen ones.
            if len(chosen_idx) < cap:
                for i in range(n):
                    if i in already:
                        continue
                    f = eligible[i]
                    chosen_idx.append((i, f"even_spacing@t={_fmt_t(f.timestamp_seconds)}"))
                    already.add(i)
                    if len(chosen_idx) >= cap:
                        break

    chosen_idx.sort(key=lambda x: eligible[x[0]].timestamp_seconds)
    sel = [
        Selected(
            path=eligible[i].path,
            timestamp_seconds=eligible[i].timestamp_seconds,
            frame_class=eligible[i].frame_class,
            reason=reason,
        )
        for i, reason in chosen_idx
    ]
    return SelectionResult(selected=sel)


def _include_for_style(frame: FrameRecord, style: str) -> bool:
    if style == "coding_agent":
        return True
    return frame.frame_class != FrameClass.CODE


def _order_for_style(pairs: list[tuple[int, FrameRecord]], style: str) -> list[tuple[int, FrameRecord]]:
    if style != "diy_project":
        return pairs
    priority = {
        FrameClass.SLIDE_TEXT: 0,
        FrameClass.UI: 1,
        FrameClass.DIAGRAM: 2,
        FrameClass.OTHER: 3,
        FrameClass.CODE: 4,
    }
    return sorted(pairs, key=lambda item: (priority[item[1].frame_class], item[1].timestamp_seconds))


def write_selected_frames_json(path: Path | str, sel: SelectionResult) -> None:
    import json
    data = {
        "selected": [
            {
                "path": s.path,
                "timestamp_seconds": s.timestamp_seconds,
                "frame_class": s.frame_class.value,
                "reason": s.reason,
            }
            for s in sel.selected
        ],
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))
