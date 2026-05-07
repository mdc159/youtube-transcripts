"""Phase 2: read extract artifacts → enrich transcript → call LLM → render output."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from manifest import Manifest, MANIFEST_FILENAME
from models import resolve, doctor, Profile
from frame_ocr import read_ocr_json, FrameClass
from frame_select import detect_scene_changes, select_frames, write_selected_frames_json
from enrichment import parse_formatted_transcript, enrich_transcript, write_enriched_transcript
from payload import build_payload, PayloadBuildError
from citation import validate_citations, extract_citations, ResolutionContext
from distill_render import render_markdown


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Distill a transcript+frames bundle through a style guide.")
    p.add_argument("title", help="Title (subdir of Generated_Data/) or absolute path to that dir")
    p.add_argument("style", help="Style name (matches styles/<style>.md)")
    p.add_argument("--model", default=None)
    p.add_argument("--max-vision-frames", type=int, default=16)
    p.add_argument("--token-budget", type=int, default=None)
    p.add_argument("--dry-run-payload", action="store_true")
    p.add_argument("--force", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    repo_root = Path(__file__).resolve().parent
    out_dir = _resolve_out_dir(args.title)
    style_path = repo_root / "styles" / f"{args.style}.md"
    if not style_path.is_file():
        print(f"style {args.style!r} not found at {style_path}", file=sys.stderr)
        return 1

    manifest_path = out_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        print(f"no manifest at {manifest_path}; run extract.py first", file=sys.stderr)
        return 1

    profile = resolve(cli=args.model, models_yaml=repo_root / "models.yaml")
    print(f"[distill] profile={profile.name} model={profile.model}")

    # Capability gate (cached); fall back to text-only on failure
    dr = doctor(profile, models_yaml=repo_root / "models.yaml", probe_image=profile.vision)
    if not dr.ok:
        print(f"[distill] doctor FAIL: {dr.failure_reason}; falling back to text-only")
        profile = Profile(**{**profile.__dict__, "vision": False})

    # Implementation continues in Task 9.2-9.5
    return 0


def _resolve_out_dir(title_or_path: str) -> Path:
    p = Path(title_or_path)
    if p.is_absolute() and p.is_dir():
        return p
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    return (base / title_or_path).resolve()


if __name__ == "__main__":
    sys.exit(main())
