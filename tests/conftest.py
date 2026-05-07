"""Shared pytest fixtures."""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def tmp_generated_data(tmp_path, monkeypatch):
    """Redirects Generated_Data writes to a tmp dir for isolation."""
    target = tmp_path / "Generated_Data"
    target.mkdir()
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(target))
    return target
