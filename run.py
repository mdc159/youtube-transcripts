"""Convenience wrapper: extract.py -> distill.py."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import distill
import extract


def main(argv=None):
    p = argparse.ArgumentParser(description="One-shot: extract then distill.")
    p.add_argument("source")
    p.add_argument("style")
    p.add_argument("--model", default=None)
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--max-vision-frames", type=int, default=16)
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--dry-run-payload", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    extract_argv = [args.source]
    if args.max_frames is not None:
        extract_argv += ["--max-frames", str(args.max_frames)]
    if args.start is not None:
        extract_argv += ["--start", str(args.start)]
    if args.end is not None:
        extract_argv += ["--end", str(args.end)]
    if args.force:
        extract_argv += ["--force"]
    rc = extract.main(extract_argv)
    if rc != 0:
        return rc

    # Resolve title from extract's output. The simplest convention: the safe
    # title is the directory name produced by extract — pick the most recently
    # modified subdir under Generated_Data.
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    subs = (
        sorted(
            (p for p in base.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if base.exists()
        else []
    )
    if not subs:
        print("no Generated_Data subdirectory found after extract", file=sys.stderr)
        return 1
    distill_argv = [subs[0].name, args.style]
    if args.model:
        distill_argv += ["--model", args.model]
    if args.max_vision_frames is not None:
        distill_argv += ["--max-vision-frames", str(args.max_vision_frames)]
    if args.dry_run_payload:
        distill_argv += ["--dry-run-payload"]
    if args.force:
        distill_argv += ["--force"]
    return distill.main(distill_argv)


if __name__ == "__main__":
    sys.exit(main())
