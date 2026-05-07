import os
import pytest
from pathlib import Path
import models


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
