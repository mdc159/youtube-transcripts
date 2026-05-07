import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
import distill


@patch("distill.OpenAI")
def test_live_distill_writes_outputs(openai_mock, tmp_path, fixtures_dir, monkeypatch):
    # Set up an extract result by writing the artifacts we need by hand.
    od = tmp_path / "T"
    od.mkdir()
    (od / "T_formatted_transcript.txt").write_text("0.0|hello\n5.0|world\n")
    (od / "T_clean_text.txt").write_text("hello world")
    (od / "frames").mkdir()
    (od / "ocr.json").write_text(json.dumps({
        "video": {"title": "T", "duration_seconds": 10},
        "frames": []
    }))
    (od / "artifact_manifest.json").write_text(json.dumps({
        "schema_version": 1, "source_id": "yt:x", "source_url": "u", "title": "T",
        "duration_seconds": 10.0, "clip_range": None, "extract": {"transcript_quality": "high"},
        "distill_runs": []
    }))
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    # Provider returns a tiny valid distill_result.json
    fake = json.dumps({
        "summary": "S",
        "key_points": [{"text": "p", "citations": ["seg#0"]}],
        "steps": [], "code_blocks": [], "tools_mentioned": [],
        "open_questions": [], "visual_evidence_used": [],
        "warnings": [],
    })
    client = openai_mock.return_value
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake))],
        usage=MagicMock(prompt_tokens=1, completion_tokens=1),
    )
    monkeypatch.setattr(distill, "doctor", lambda *a, **k: type("R", (), {"ok": True})())
    rc = distill.main(["T", "knowledge_base"])
    assert rc == 0
    assert (od / "T_knowledge_base.md").is_file()
    assert (od / "T_knowledge_base.distill_result.json").is_file()


@patch("distill.OpenAI")
def test_distill_fails_on_unresolved_citations(openai_mock, tmp_path, monkeypatch):
    od = tmp_path / "T"
    od.mkdir()
    (od / "T_formatted_transcript.txt").write_text("0.0|hi\n")
    (od / "ocr.json").write_text(json.dumps({"video": {"title":"T","duration_seconds":1}, "frames": []}))
    (od / "artifact_manifest.json").write_text(json.dumps({"schema_version":1,"source_id":"x","source_url":"u","title":"T","duration_seconds":1.0,"clip_range":None,"extract":{"transcript_quality":"high"},"distill_runs":[]}))
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(distill, "doctor", lambda *a, **k: type("R", (), {"ok": True})())
    fake = json.dumps({
        "summary": "S — see seg#9999 and frame_999",  # both unresolved
        "key_points": [], "steps": [], "code_blocks": [],
        "tools_mentioned": [], "open_questions": [], "visual_evidence_used": [], "warnings": [],
    })
    openai_mock.return_value.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake))],
        usage=MagicMock(prompt_tokens=1, completion_tokens=1),
    )
    rc = distill.main(["T", "knowledge_base"])
    assert rc == 1
    # Files still written, but flagged
    md = (od / "T_knowledge_base.md").read_text()
    assert "unresolved citations" in md
