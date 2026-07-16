"""Regenerate the dry-run payload golden files.

Run when the prompt contract or one of the bundled style overlays changes by
design. Mirrors what tests/integration/test_golden.py does at test time.

Usage:
    uv run python scripts/regen_golden_payloads.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from yt_distill.pipeline import distill  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "golden"
SCENARIOS = ["coding_video", "slide_talk", "ui_demo", "local_file"]


def _stub_doctor(*_a, **_kw):
    return type("R", (), {"ok": True, "failure_reason": ""})()


def main() -> int:
    distill.doctor = _stub_doctor  # type: ignore[assignment]
    for scenario in SCENARIOS:
        src = GOLDEN / scenario / "inputs"
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "data"
            shutil.copytree(src, stage)
            import os
            os.environ["YT_GENERATED_DATA_DIR"] = str(stage)
            rc = distill.main(["Test", "knowledge_base", "--dry-run-payload", "--model", "gemini-3-flash"])
            if rc != 0:
                print(f"distill returned {rc} for {scenario}", file=sys.stderr)
                return rc
            payload = json.loads((stage / "Test" / "payload.json").read_text())
            (GOLDEN / scenario / "payload.golden.json").write_text(json.dumps(payload, indent=2))
            print(f"refreshed {scenario}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
