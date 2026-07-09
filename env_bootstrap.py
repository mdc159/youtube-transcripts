"""Load the repo-root .env into os.environ (existing env vars win).

Entry points call load() so API keys in .env work for every phase CLI —
including when invoked from another cwd (paths resolve against this file,
not the working directory). Missing .env / missing python-dotenv are no-ops.
"""
from __future__ import annotations

from pathlib import Path


def load() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dep
        return
    load_dotenv(Path(__file__).resolve().parent / ".env")
