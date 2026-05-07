"""Frame OCR with per-line confidence gating, 5-class classification, and dedup."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rapidocr_onnxruntime import RapidOCR

CONFIDENCE_GATE = 0.5

_OCR: Optional[RapidOCR] = None


def _ocr() -> RapidOCR:
    global _OCR
    if _OCR is None:
        _OCR = RapidOCR()
    return _OCR


@dataclass
class OcrLine:
    text: str
    confidence: float
    above_gate: bool


@dataclass
class OcrResult:
    text: str
    high_confidence_text: str
    lines: list[OcrLine]
    mean_confidence: float


def ocr_frame(path: Path | str) -> OcrResult:
    path = str(path)
    raw, _ = _ocr()(path)
    lines: list[OcrLine] = []
    for entry in raw or []:
        # entry shape: [bbox, text, confidence]
        text = (entry[1] or "").strip()
        conf = float(entry[2]) if entry[2] is not None else 0.0
        if not text:
            continue
        lines.append(OcrLine(text=text, confidence=conf, above_gate=conf >= CONFIDENCE_GATE))
    text = "\n".join(l.text for l in lines)
    high = "\n".join(l.text for l in lines if l.above_gate)
    mean = sum(l.confidence for l in lines) / len(lines) if lines else 0.0
    return OcrResult(text=text, high_confidence_text=high, lines=lines, mean_confidence=mean)


import enum


class FrameClass(str, enum.Enum):
    CODE = "code"
    SLIDE_TEXT = "slide_text"
    UI = "ui"
    DIAGRAM = "diagram"
    OTHER = "other"


_CODE_GLYPHS = set("{}[]()<>;=")
_KEYWORDS = re.compile(r"(?:^|\s)(?:def |function |class |import |from |const |let |var |return |if \(|// |# )")


def _signal_glyph_density(text: str) -> bool:
    n = max(1, len(text))
    return sum(1 for c in text if c in _CODE_GLYPHS) * 100 / n >= 3


def _signal_indentation(text: str) -> bool:
    return sum(1 for ln in text.splitlines() if ln.startswith("  ") or ln.startswith("\t")) >= 3


def _signal_keywords(text: str) -> bool:
    return _KEYWORDS.search(text) is not None


def _signal_line_uniformity(lines: list[OcrLine]) -> bool:
    if len(lines) < 5:
        return False
    leadings = [ln.text.lstrip()[:1] if ln.text.strip() else "" for ln in lines]
    if not leadings:
        return False
    most = max(set(leadings), key=leadings.count)
    return leadings.count(most) >= 5


def classify_frame(res: OcrResult) -> tuple[FrameClass, float]:
    """Return (class, class_confidence)."""
    text = res.high_confidence_text or res.text
    n_lines = len(res.lines)
    code_signals = sum([
        _signal_glyph_density(text),
        _signal_indentation(text),
        _signal_keywords(text),
        _signal_line_uniformity(res.lines),
    ])
    if code_signals >= 2:
        return FrameClass.CODE, min(1.0, 0.5 + 0.15 * code_signals)

    # Heuristics for the remaining classes
    text_density = len(text) / max(1, n_lines)
    if n_lines >= 4 and text_density > 12 and not _signal_glyph_density(text):
        return FrameClass.SLIDE_TEXT, 0.7
    short_label_lines = sum(1 for ln in res.lines if 0 < len(ln.text) <= 24)
    if n_lines >= 2 and short_label_lines == n_lines and not _signal_glyph_density(text):
        return FrameClass.UI, 0.65
    if n_lines <= 2 and not _signal_glyph_density(text):
        return FrameClass.DIAGRAM, 0.55  # below the 0.6 gate -> caller will treat as OTHER

    return FrameClass.OTHER, 0.5


# Caller convention: if class_confidence < 0.6, treat as OTHER (spec §4.3).


from rapidfuzz import fuzz


@dataclass
class FrameRecord:
    path: str
    timestamp_seconds: float
    ocr_text: str
    ocr_confidence: float
    frame_class: FrameClass
    class_confidence: float
    cluster_id: Optional[str] = None
    ocr_error: Optional[str] = None


def _normalize(text: str) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(r"[#].*$", "", s, flags=re.MULTILINE)  # strip line comments
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
    return s


def dedup_code_frames(frames: list[FrameRecord], similarity: float = 0.9) -> list[FrameRecord]:
    """Cluster CODE-class frames by normalized OCR text (rapidfuzz token-set ratio)."""
    next_id = 0
    cluster_reps: list[tuple[str, str]] = []  # (cluster_id, normalized_text)
    out = []
    for f in frames:
        if f.frame_class != FrameClass.CODE:
            out.append(f)
            continue
        norm = _normalize(f.ocr_text)
        match_id: Optional[str] = None
        for cid, rep in cluster_reps:
            if fuzz.token_set_ratio(norm, rep) / 100.0 >= similarity:
                match_id = cid
                break
        if match_id is None:
            match_id = f"c{next_id}"
            next_id += 1
            cluster_reps.append((match_id, norm))
        out.append(FrameRecord(**{**f.__dict__, "cluster_id": match_id}))
    return out
