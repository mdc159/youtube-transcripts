"""Per-entry-point bootstrap: .env loading + DNS resilience.

Entry points call load() so (a) API keys in the repo-root .env work for every
phase CLI regardless of cwd, and (b) the DoH DNS fallback is armed — networks
that hijack port-53 and filter hosts can't silently break reference
harvesting. Missing .env / missing python-dotenv are no-ops.
"""
from __future__ import annotations

from pathlib import Path


def load() -> None:
    import dns_fallback

    dns_fallback.install()
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dep
        return
    load_dotenv(Path(__file__).resolve().parent / ".env")
