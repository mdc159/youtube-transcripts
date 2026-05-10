"""Phase 2: read extract artifacts → enrich transcript → call LLM → render output."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from openai import OpenAI

from manifest import Manifest, MANIFEST_FILENAME
from models import resolve, doctor, Profile
from frame_ocr import read_ocr_json, FrameClass
from frame_select import detect_scene_changes, select_frames, write_selected_frames_json
from enrichment import parse_formatted_transcript, enrich_transcript, write_enriched_transcript
from payload import build_payload, PayloadBuildError
from citation import validate_citations, extract_citations, ResolutionContext
from distill_render import render_markdown
from video_profile import VideoProfile, build_video_profile, format_route_proposal


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
    style_path = None
    if args.style != "auto":
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

    style_name, route_profile = _route_style(
        args.style,
        title=out_dir.name,
        segments=segments,
        frames=frames,
    )
    if route_profile is not None:
        print(f"[distill] auto route:\n{format_route_proposal(route_profile)}")
    style_path = style_path or repo_root / "styles" / f"{style_name}.md"
    if not style_path.is_file():
        print(f"style {style_name!r} not found at {style_path}", file=sys.stderr)
        return 1

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
        style=style_name,
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

    # Live distillation
    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        print(f"missing API key {profile.api_key_env}", file=sys.stderr)
        return 1
    client = OpenAI(base_url=profile.base_url, api_key=api_key)
    create_kwargs = dict(model=profile.model, messages=[{"role": "user", "content": content}])
    if profile.reasoning:
        create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}
    response = client.chat.completions.create(**create_kwargs)

    msg = response.choices[0].message.content or ""
    if not msg.strip():
        raise ValueError("provider returned empty content")

    # The contract instructs the model to return a *markdown* note. We re-derive
    # distill_result.json from the markdown's structure for downstream tooling.
    # In v1 we accept either:
    #   - a JSON object the model produced (preferred), or
    #   - the markdown directly, which we wrap.
    parsed = _try_parse_json_object(msg)
    manifest_data = json.loads(manifest_path.read_text())
    manifest = Manifest(out_dir=out_dir, data=manifest_data)
    cit_ctx = ResolutionContext(
        segment_ids={s.seg_id for s in segments},
        frame_ids={Path(f.path).stem for f in frames},
        cluster_ids={f.cluster_id for f in frames if f.cluster_id},
    )
    val = validate_citations(msg, cit_ctx)
    parsed_full = {
        "schema_version": 1,
        "source_id": manifest.data["source_id"],
        "title": manifest.data["title"],
        "model_profile": profile.name,
        "prompt_contract_version": 1,
        **(parsed or {"summary": msg}),
        "quality": {
            "transcript": (manifest.data.get("extract") or {}).get("transcript_quality", "unknown"),
            "ocr": "unknown",
            "frame_coverage": "unknown",
            "distillation_confidence": _confidence_from(val.unresolved, manifest),
        },
        "warnings": parsed.get("warnings", []) if parsed else [],
        "token_usage": {
            "prompt": getattr(response.usage, "prompt_tokens", None),
            "completion": getattr(response.usage, "completion_tokens", None),
            "image_count": sum(1 for c in content if c["type"] == "image_url"),
        },
        "citations": {
            "segments_referenced": sum(1 for c in val.citations if c.kind == "segment"),
            "frames_referenced": sum(1 for c in val.citations if c.kind == "frame"),
            "unresolved": len(val.unresolved),
        },
    }

    today_iso = date.today().isoformat()
    md = render_markdown(parsed_full, style_name=style_name, today_iso=today_iso)
    (out_dir / f"{out_dir.name}_{style_name}.md").write_text(md)
    (out_dir / f"{out_dir.name}_{style_name}.distill_result.json").write_text(json.dumps(parsed_full, indent=2))

    # Citation validator gate
    if val.unresolved:
        print(
            f"[distill] WARNING: {len(val.unresolved)} unresolved citations: "
            f"{[c.raw for c in val.unresolved]}",
            file=sys.stderr,
        )
        return 1
    return 0


def _try_parse_json_object(text: str) -> dict | None:
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _route_style(
    requested_style: str,
    *,
    title: str,
    segments: list,
    frames: list,
) -> tuple[str, VideoProfile | None]:
    if requested_style != "auto":
        return requested_style, None
    transcript_text = "\n".join(getattr(seg, "text", "") for seg in segments)
    profile = build_video_profile(
        title=title,
        transcript_text=transcript_text,
        frames=frames,
    )
    return profile.recommended_style, profile


def _confidence_from(unresolved: list, manifest: Manifest) -> str:
    if unresolved:
        return "low"
    if (manifest.data.get("extract") or {}).get("transcript_quality") == "high":
        return "high"
    return "medium"


def _resolve_out_dir(title_or_path: str) -> Path:
    p = Path(title_or_path)
    if p.is_absolute() and p.is_dir():
        return p
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    return (base / title_or_path).resolve()


if __name__ == "__main__":
    sys.exit(main())
