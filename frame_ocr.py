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
