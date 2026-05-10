"""Lightweight routing profile for choosing a video distillation workflow."""
from __future__ import annotations

import re
from dataclasses import dataclass

from frame_ocr import FrameClass, FrameRecord

STYLE_CODING = "coding_agent"
STYLE_DIY = "diy_project"
STYLE_KNOWLEDGE = "knowledge_base"
STYLES = (STYLE_CODING, STYLE_DIY, STYLE_KNOWLEDGE)


_CODING_TERMS = (
    "api",
    "class",
    "cli",
    "command",
    "component",
    "database",
    "endpoint",
    "function",
    "install",
    "package",
    "python",
    "repo",
    "sdk",
    "test",
)
_DIY_TERMS = (
    "attach",
    "board",
    "bolt",
    "clamp",
    "cut",
    "drill",
    "hinge",
    "materials",
    "plywood",
    "prototype",
    "sand",
    "screw",
    "sensor",
    "solder",
    "safety",
    "wire",
)
_KNOWLEDGE_TERMS = (
    "architecture",
    "concept",
    "conceptual",
    "design",
    "framework",
    "mental model",
    "overview",
    "patterns",
    "principles",
    "strategy",
    "system",
    "talk",
    "tradeoffs",
)

_COMMAND_OR_PATH_RE = re.compile(
    r"(?:\b(?:uv|npm|pnpm|yarn|pip|python|git|docker)\s+\w+|\b\w+/\w+|\b\w+\.(?:py|ts|tsx|js|json|yaml|yml)\b)"
)
_MEASUREMENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:inches|inch|ft|feet|mm|cm|m|x\d+|degrees)\b")


@dataclass(frozen=True)
class VideoProfile:
    recommended_style: str
    confidence: float
    needs_confirmation: bool
    scores: dict[str, float]
    signals: dict[str, dict[str, int]]
    alternatives: list[str]


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def _signal_counts(text: str, frames: list[FrameRecord]) -> dict[str, dict[str, int]]:
    code_frames = sum(1 for f in frames if f.frame_class == FrameClass.CODE)
    slide_or_diagram_frames = sum(1 for f in frames if f.frame_class in {FrameClass.SLIDE_TEXT, FrameClass.DIAGRAM})
    cluster_count = len({f.cluster_id for f in frames if f.cluster_id})
    command_or_path_hits = len(_COMMAND_OR_PATH_RE.findall(text))
    measurement_hits = len(_MEASUREMENT_RE.findall(text))

    return {
        STYLE_CODING: {
            "keyword_hits": _count_terms(text, _CODING_TERMS),
            "command_or_path_hits": command_or_path_hits,
            "code_frames": code_frames,
            "code_clusters": cluster_count,
        },
        STYLE_DIY: {
            "keyword_hits": _count_terms(text, _DIY_TERMS),
            "measurement_hits": measurement_hits,
            "visual_step_frames": slide_or_diagram_frames,
        },
        STYLE_KNOWLEDGE: {
            "keyword_hits": _count_terms(text, _KNOWLEDGE_TERMS),
            "slide_or_diagram_frames": slide_or_diagram_frames,
        },
    }


def _score(signals: dict[str, dict[str, int]]) -> dict[str, float]:
    coding = signals[STYLE_CODING]
    diy = signals[STYLE_DIY]
    knowledge = signals[STYLE_KNOWLEDGE]

    scores = {
        STYLE_CODING: (
            coding["keyword_hits"]
            + 1.5 * coding["command_or_path_hits"]
            + 3.0 * coding["code_frames"]
            + 1.5 * coding["code_clusters"]
        ),
        STYLE_DIY: (
            diy["keyword_hits"]
            + 2.0 * diy["measurement_hits"]
            + 0.75 * diy["visual_step_frames"]
        ),
        STYLE_KNOWLEDGE: (
            knowledge["keyword_hits"]
            + 0.75 * knowledge["slide_or_diagram_frames"]
        ),
    }

    # If there are few concrete coding/DIY signals, conceptual videos should
    # route to the broad note-taking workflow instead of appearing low signal.
    if scores[STYLE_KNOWLEDGE] > 0 and scores[STYLE_CODING] < 3 and scores[STYLE_DIY] < 3:
        scores[STYLE_KNOWLEDGE] += 2.0
    return scores


def build_video_profile(
    *,
    title: str,
    transcript_text: str,
    frames: list[FrameRecord],
) -> VideoProfile:
    """Choose the most likely distillation style from cheap artifact signals."""
    frame_text = "\n".join(f.ocr_text for f in frames)
    text = "\n".join([title, transcript_text, frame_text]).lower()
    signals = _signal_counts(text, frames)
    scores = _score(signals)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    total = sum(max(score, 0.0) for score in scores.values())
    if total == 0:
        return VideoProfile(
            recommended_style=STYLE_KNOWLEDGE,
            confidence=0.0,
            needs_confirmation=True,
            scores={style: round(score, 2) for style, score in scores.items()},
            signals=signals,
            alternatives=[],
        )

    top_style, top_score = ranked[0]
    confidence = round((top_score / total) if total else 0.0, 2)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (top_score - second_score) / max(top_score, 1.0)
    needs_confirmation = confidence < 0.7 or margin < 0.3
    alternatives = [style for style, score in ranked[1:] if score > 0]

    return VideoProfile(
        recommended_style=top_style,
        confidence=confidence,
        needs_confirmation=needs_confirmation,
        scores={style: round(score, 2) for style, score in scores.items()},
        signals=signals,
        alternatives=alternatives,
    )


def format_route_proposal(profile: VideoProfile) -> str:
    """Human-readable routing explanation for ambiguous or auto-routed runs."""
    best = profile.recommended_style
    best_signals = profile.signals[best]
    signal_summary = ", ".join(f"{name}={value}" for name, value in best_signals.items() if value)
    if not signal_summary:
        signal_summary = "weak explicit signals"
    alternatives = ", ".join(profile.alternatives) if profile.alternatives else "none"
    return (
        f"Recommended style: {best} (confidence={profile.confidence:.2f}).\n"
        f"Reason: strongest signals were {signal_summary}.\n"
        f"Alternative styles: {alternatives}."
    )
