"""Per-entry-point bootstrap: .env loading + DNS resilience.

Entry points call load() so (a) API keys in the repo-root .env work for every
phase CLI regardless of cwd, and (b) the DoH DNS fallback is armed — networks
that hijack port-53 and filter hosts can't silently break reference
harvesting. Missing .env / missing python-dotenv are no-ops.
"""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    # Walk up from this file: works for both src-layout editable installs
    # (repo/src/yt_distill/...) and .venv installs (repo/.venv/...), since
    # pyproject.toml marks the repo root in both. The old parents[N]
    # arithmetic resolved to the wrong directory for .venv installs.
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
        if parent.name == "site-packages":
            break  # global install: no repo root above; don't mis-root on a stray pyproject
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
