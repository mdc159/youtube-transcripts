"""Stage registry — the modular core of the pipeline.

A *stage* is one processing/enrichment capability. Stages declare what
artifacts they need (`requires`), what they write (`produces`), and how
expensive they are (`cost_tier`). `runnable()` returns stages ordered
economical-first, which makes the escalation principle structural: callers
start at FREE and only raise `max_tier` when a cheaper pass left gaps.

Adding a new enrichment tool later = one module registering one Stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Callable


class CostTier(IntEnum):
    FREE = 0            # cached/remote-free data (e.g. caption APIs)
    LOCAL_COMPUTE = 1   # ffmpeg, OCR, perceptual hashing
    CHEAP_LLM = 2       # text-only LLM calls
    VISION_LLM = 3      # multimodal LLM calls


@dataclass
class StageContext:
    title_dir: Path
    options: dict


@dataclass
class StageResult:
    produced: dict[str, Path]
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Stage:
    name: str
    cost_tier: CostTier
    requires: frozenset[str]
    produces: frozenset[str]
    run: Callable[[StageContext], StageResult]


_REGISTRY: dict[str, Stage] = {}


def register(stage: Stage) -> Stage:
    if stage.name in _REGISTRY:
        raise RuntimeError(f"stage already registered: {stage.name}")
    _REGISTRY[stage.name] = stage
    return stage


def get(name: str) -> Stage:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise RuntimeError(f"unknown stage: {name}") from None


def all_stages() -> list[Stage]:
    return sorted(_REGISTRY.values(), key=lambda s: (s.cost_tier, s.name))


def runnable(available: set[str], max_tier: CostTier = CostTier.VISION_LLM) -> list[Stage]:
    """Stages whose requirements are met, cheapest first."""
    return [
        s for s in all_stages()
        if s.cost_tier <= max_tier and s.requires <= available
    ]


def clear() -> None:
    """Test helper: reset the registry."""
    _REGISTRY.clear()
