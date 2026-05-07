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
