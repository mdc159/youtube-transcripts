"""Per-entry-point bootstrap: .env loading + DNS resilience.

Entry points call load() so (a) API keys in the repo-root .env work for every
phase CLI regardless of cwd, and (b) the DoH DNS fallback is armed — networks
that hijack port-53 and filter hosts can't silently break reference
harvesting. Missing .env / missing python-dotenv are no-ops.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def load() -> None:
    from yt_distill.core import dns_fallback

    dns_fallback.install()
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dep
        return
    load_dotenv(REPO_ROOT / ".env")
