import json
import os
from pathlib import Path
import pytest
import distill, extract


@pytest.mark.integration
def test_dry_run_payload_flow(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    extract.main([str(src), "--max-frames", "6"])
    od = next(tmp_path.iterdir())
    # Skip the doctor by mocking it
    import distill as _d
    monkeypatch.setattr(_d, "doctor", lambda *a, **k: type("R", (), {"ok": True, "failure_reason": ""})())
    rc = distill.main([od.name, "knowledge_base", "--dry-run-payload"])
    assert rc == 0
    payload_path = od / "payload.json"
    assert payload_path.is_file()
    payload = json.loads(payload_path.read_text())
    assert any(c["type"] == "text" for c in payload)
