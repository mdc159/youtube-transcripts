import os
from unittest.mock import patch, MagicMock

import pytest
from pathlib import Path

import models
from models import doctor, DoctorResult


def test_resolve_default(monkeypatch, repo_root):
    monkeypatch.delenv("DISTILL_MODEL", raising=False)
    p = models.resolve(cli=None, models_yaml=repo_root / "models.yaml")
    assert p.name == "gemini-3-flash"


def test_resolve_env_overrides_default(monkeypatch, repo_root):
    monkeypatch.setenv("DISTILL_MODEL", "gemini-3-pro")
    p = models.resolve(cli=None, models_yaml=repo_root / "models.yaml")
    assert p.name == "gemini-3-pro"


def test_resolve_cli_overrides_env(monkeypatch, repo_root):
    monkeypatch.setenv("DISTILL_MODEL", "gemini-3-pro")
    p = models.resolve(cli="claude-sonnet-4-6", models_yaml=repo_root / "models.yaml")
    assert p.name == "claude-sonnet-4-6"


def test_unknown_profile_lists_available(repo_root):
    with pytest.raises(SystemExit) as ei:
        models.resolve(cli="nonexistent", models_yaml=repo_root / "models.yaml")
    assert "available" in str(ei.value).lower() or "nonexistent" in str(ei.value)


def _ok_response(content="hello"):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


@patch("models.OpenAI")
def test_doctor_ok_text_only(openai_mock, monkeypatch, tmp_path, repo_root):
    monkeypatch.setattr("models._cache_dir", lambda: tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = openai_mock.return_value
    client.chat.completions.create.return_value = _ok_response("hi")
    p = models.resolve(cli="claude-sonnet-4-6", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml", probe_image=False)
    assert res.ok is True
    assert res.text_probe is True


@patch("models.OpenAI")
def test_doctor_missing_key(openai_mock, monkeypatch, tmp_path, repo_root):
    monkeypatch.setattr("models._cache_dir", lambda: tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = models.resolve(cli="gemini-3-flash", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml")
    assert res.ok is False
    assert "key" in res.failure_reason.lower()


@patch("models.OpenAI")
def test_doctor_text_failure_reports(openai_mock, monkeypatch, tmp_path, repo_root):
    monkeypatch.setattr("models._cache_dir", lambda: tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = openai_mock.return_value
    client.chat.completions.create.side_effect = RuntimeError("boom")
    p = models.resolve(cli="gemini-3-flash", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml", probe_image=False)
    assert res.ok is False
    assert "boom" in res.failure_reason
