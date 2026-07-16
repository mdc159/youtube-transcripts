"""Golden-output regression tests.

For each of four representative input trees (coding_video, slide_talk, ui_demo,
local_file) we run distill in --dry-run-payload mode and compare the produced
payload against a checked-in golden file. Image bytes are elided in dry-run, so
the comparison is structural (text blocks + image-url placeholders).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from yt_distill.pipeline import distill


GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
SCENARIOS = ["coding_video", "slide_talk", "ui_demo", "local_file"]


def _normalize(payload: list[dict]) -> list[dict]:
    """Strip details that legitimately vary across runs.

    Image bytes are already elided to `<elided:image_N>` by --dry-run-payload,
    so the URL is structural. Text blocks compare verbatim — golden files were
    captured from the same inputs and contain no absolute paths or timestamps.
    """
    out: list[dict] = []
    for c in payload:
        if c["type"] == "text":
            out.append({"type": "text", "text": c["text"]})
        else:
            out.append({"type": "image_url", "image_url": {"url": c["image_url"]["url"]}})
    return out


@pytest.mark.integration
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_dry_run_payload_matches_golden(scenario, tmp_path, monkeypatch):
    src = GOLDEN / scenario / "inputs"
    stage = tmp_path / "data"
    shutil.copytree(src, stage)
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(stage))
    monkeypatch.setattr(
        distill,
        "doctor",
        lambda *a, **k: type("R", (), {"ok": True, "failure_reason": ""})(),
    )

    rc = distill.main(["Test", "knowledge_base", "--dry-run-payload", "--model", "gemini-3-flash"])
    assert rc == 0, f"distill returned {rc} for {scenario}"

    actual = json.loads((stage / "Test" / "payload.json").read_text())
    expected = json.loads((GOLDEN / scenario / "payload.golden.json").read_text())
    assert _normalize(actual) == _normalize(expected), f"golden drift in {scenario}"
