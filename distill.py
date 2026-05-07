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

    # Load artifacts
    formatted_path = out_dir / f"{out_dir.name}_formatted_transcript.txt"
    if not formatted_path.is_file():
        print(f"missing transcript: {formatted_path}", file=sys.stderr)
        return 1
    segments = parse_formatted_transcript(formatted_path)
    ocr_path = out_dir / "ocr.json"
    frames = read_ocr_json(ocr_path) if ocr_path.is_file() else []

    # Enrich
    enriched = enrich_transcript(segments, frames)
    enriched_path = out_dir / f"{out_dir.name}_enriched_transcript.md"
    write_enriched_transcript(enriched_path, enriched)

    # Frame selection
    frame_paths = [out_dir / f.path for f in frames]
    cps = detect_scene_changes(frame_paths) if frame_paths else []
    sel = select_frames(
        frames,
        change_points=cps,
        max_frames=args.max_vision_frames,
        token_budget=args.token_budget,
    )
    write_selected_frames_json(out_dir / "selected_frames.json", sel)

    # Build payload
    contract = (Path(__file__).resolve().parent / "prompts" / "distill_contract_v1.md").read_text()
    style = style_path.read_text()
    try:
        content = build_payload(
            profile=profile,
            system_prompt=contract,
            style=style,
            enriched_transcript=enriched,
            selected=sel.selected,
            frames_root=out_dir,
        )
    except PayloadBuildError as e:
        print(f"[distill] payload build failed: {e}", file=sys.stderr)
        return 1

    if args.dry_run_payload:
        # Write payload with image bytes elided to file refs for inspection
        elided = []
        img_idx = 0
        for c in content:
            if c["type"] == "image_url":
                elided.append({"type": "image_url", "image_url": {"url": f"<elided:image_{img_idx}>"}})
                img_idx += 1
            else:
                elided.append(c)
        (out_dir / "payload.json").write_text(json.dumps(elided, indent=2))
        print(f"[distill] dry-run payload written to {out_dir / 'payload.json'}")
        return 0

    # API call + rendering = Task 9.3
    print("[distill] live distillation not yet implemented — see Task 9.3")
    return 0


def _resolve_out_dir(title_or_path: str) -> Path:
    p = Path(title_or_path)
    if p.is_absolute() and p.is_dir():
        return p
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    return (base / title_or_path).resolve()


if __name__ == "__main__":
    sys.exit(main())
