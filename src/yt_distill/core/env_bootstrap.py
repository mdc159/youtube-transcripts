"""Per-entry-point bootstrap: .env loading + DNS resilience.

Entry points call load() so (a) API keys in the repo-root .env work for every
phase CLI regardless of cwd, and (b) the DoH DNS fallback is armed — networks
that hijack port-53 and filter hosts can't silently break reference
harvesting. Missing .env / missing python-dotenv are no-ops.
"""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    # Walk up from this file to the first pyproject.toml: works for src-layout
    # editable installs (repo/src/yt_distill/...), project-venv installs
    # (repo/.venv/.../site-packages/...), and global installs (no pyproject
    # ancestor → fallback). Do NOT stop at site-packages: project venvs put
    # the repo root above it. The old parents[N] arithmetic mis-rooted for
    # .venv installs.
    # ponytail: a stray pyproject.toml above a global Python install would
    # mis-root; no known real case — tighten if one appears.
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()


def load() -> None:
    from yt_distill.core import dns_fallback

    dns_fallback.install()
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dep
        return
    load_dotenv(REPO_ROOT / ".env")
