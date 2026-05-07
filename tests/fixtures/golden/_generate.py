"""Build the four golden fixture trees.

Run once: `uv run python tests/fixtures/golden/_generate.py`

Each scenario produces an `inputs/Test/` tree with:
  - Test_formatted_transcript.txt   (timestamp|text per line)
  - Test_clean_text.txt             (plain text)
  - artifact_manifest.json          (extract phase manifest)
  - frames/frame_NNN_t-MM-SS.jpg    (synthetic frames keyed to the OCR records)
  - ocr.json                        (per-scenario OCR + class results)

Scenarios:
  coding_video — code-class frames with cluster_id
  slide_talk   — slide_text-class frames
  ui_demo      — ui-class frames
  local_file   — no OCR records (text-only path)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
FONT = ImageFont.load_default()
SCENARIOS = ["coding_video", "slide_talk", "ui_demo", "local_file"]


def _frame(path: Path, lines: list[str]) -> None:
    img = Image.new("RGB", (512, 384), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((10, 10 + i * 16), ln, fill=(0, 0, 0), font=FONT)
    img.save(path, "JPEG", quality=85)


def build(scenario: str) -> None:
    inputs = ROOT / scenario / "inputs"
    if inputs.exists():
        shutil.rmtree(inputs)
    inputs.mkdir(parents=True)
    od = inputs / "Test"
    (od / "frames").mkdir(parents=True)

    # Transcript artifacts (deterministic + small)
    (od / "Test_formatted_transcript.txt").write_text("0.0|Hello world\n5.0|How are you\n")
    (od / "Test_clean_text.txt").write_text("Hello world How are you")
    (od / "artifact_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_id": f"yt:{scenario}",
                "source_url": "u",
                "title": "Test",
                "duration_seconds": 10.0,
                "clip_range": None,
                "extract": {"transcript_quality": "high"},
                "distill_runs": [],
            },
            indent=2,
            sort_keys=True,
        )
    )

    # Per-scenario frames + ocr.json
    if scenario == "coding_video":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(
                od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                ["def f():", "    return 1", "", "x = f()"],
            )
        ocr_frames = [
            {
                "path": "frames/frame_000_t-00-01.jpg",
                "timestamp_seconds": 1.0,
                "ocr_text": "def f():\n    return 1\n\nx = f()",
                "ocr_confidence": 0.9,
                "frame_class": "code",
                "class_confidence": 0.9,
                "cluster_id": "c0",
                "ocr_error": None,
            },
        ]
    elif scenario == "slide_talk":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(
                od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                ["RAG Pipelines", "Step 1", "Step 2", "Step 3", "Step 4"],
            )
        ocr_frames = [
            {
                "path": "frames/frame_000_t-00-01.jpg",
                "timestamp_seconds": 1.0,
                "ocr_text": "RAG Pipelines\nStep 1\nStep 2",
                "ocr_confidence": 0.9,
                "frame_class": "slide_text",
                "class_confidence": 0.7,
                "cluster_id": None,
                "ocr_error": None,
            },
        ]
    elif scenario == "ui_demo":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(
                od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                ["Settings", "Save", "Cancel"],
            )
        ocr_frames = [
            {
                "path": "frames/frame_000_t-00-01.jpg",
                "timestamp_seconds": 1.0,
                "ocr_text": "Settings\nSave\nCancel",
                "ocr_confidence": 0.85,
                "frame_class": "ui",
                "class_confidence": 0.65,
                "cluster_id": None,
                "ocr_error": None,
            },
        ]
    else:  # local_file
        for i, ts in enumerate([1.0, 5.0]):
            _frame(od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg", ["misc"])
        ocr_frames = []

    (od / "ocr.json").write_text(
        json.dumps(
            {"video": {"title": "Test", "duration_seconds": 10}, "frames": ocr_frames},
            indent=2,
        )
    )


if __name__ == "__main__":
    for s in SCENARIOS:
        build(s)
    print("ok")
