"""Phase 1: download → transcript → frames → OCR → manifest.

Idempotent. Re-runs skip completed steps unless --force / --force-ocr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from manifest import derive_source_id, Manifest


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract transcript, frames, and OCR for a video source.")
    p.add_argument("source", help="URL or local path")
    p.add_argument("--out-dir", default=None, help="Override Generated_Data root")
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--no-frames", action="store_true")
    p.add_argument("--keep-video", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-run all steps")
    p.add_argument("--force-ocr", action="store_true", help="Re-run OCR only")
    p.add_argument("--cookies-from-browser", default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    source_id = derive_source_id(args.source, start=args.start, end=args.end)
    print(f"[extract] source_id={source_id}")
    # The orchestration pipeline is filled in across Tasks 6.2 - 6.5.
    return 0


if __name__ == "__main__":
    sys.exit(main())
