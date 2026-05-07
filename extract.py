"""Phase 1: download → transcript → frames → OCR → manifest.

Idempotent. Re-runs skip completed steps unless --force / --force-ocr.
"""
from __future__ import annotations

import argparse
import json as _json
import os
import re
import subprocess
import sys
from pathlib import Path

from manifest import derive_source_id, Manifest
from transcript import fetch_transcript


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

    title, duration_seconds, source_url = _probe_source(args.source)
    out_root = Path(args.out_dir or os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    out_dir = out_root / title
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[extract] out_dir={out_dir}")

    manifest = Manifest.load_or_create(
        out_dir,
        source_id=source_id,
        source_url=source_url,
        title=title,
        duration_seconds=duration_seconds,
    )

    # Step 1: transcript (always; idempotent via manifest)
    if (
        not args.force
        and manifest.data.get("extract")
        and manifest.file_intact("extract", "formatted_transcript")
    ):
        print("[extract] transcript: skipping (already complete)")
    else:
        _do_transcript(args, out_dir, manifest)

    # Step 2: frames (skipped on --no-frames)
    if not args.no_frames:
        _do_frames(args, out_dir, manifest)
        # OCR + classification wired in Task 6.3.

    manifest.save()
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_source(source: str) -> tuple[str, float, str]:
    """Return (safe_title, duration_seconds, canonical_url_or_path).

    Local files are detected via Path.exists() FIRST so we don't try to ask
    yt-dlp about them.
    """
    if Path(source).exists():
        title = Path(source).stem
        duration = _ffprobe_duration(source)
        return _safe_title(title), duration, str(Path(source).resolve())

    # Probe URL via yt-dlp --dump-json
    r = subprocess.run(
        ["yt-dlp", "--no-warnings", "--dump-json", source],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"yt-dlp probe failed: {r.stderr}")
    info = _json.loads(r.stdout)
    return (
        _safe_title(info.get("title") or info.get("id") or "video"),
        float(info.get("duration") or 0.0),
        info.get("webpage_url") or source,
    )


def _safe_title(t: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", t).strip()
    return re.sub(r"[-\s]+", "_", safe)


def _ffprobe_duration(path: str) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip() or 0.0)


def _do_transcript(args, out_dir: Path, manifest: Manifest) -> None:
    """Run the 4-tier chain. Whisper requires audio extraction (TODO Task 6.4)."""
    res = fetch_transcript(args.source, allow_whisper=False)
    base = out_dir / out_dir.name
    formatted = Path(str(base) + "_formatted_transcript.txt")
    clean = Path(str(base) + "_clean_text.txt")
    if res is None:
        formatted.write_text("# transcript_unavailable\n")
        clean.write_text("# transcript_unavailable\n")
        manifest.set_extract(
            {"transcript_source": "none", "transcript_quality": "none", "files": {}}
        )
        return
    formatted.write_text("\n".join(f"{ts}|{txt}" for ts, txt in res.entries) + "\n")
    clean.write_text(_format_clean(res.entries))
    manifest.set_extract(
        {
            "transcript_source": res.source,
            "transcript_quality": _grade_transcript(res.source),
            "files": {},
        }
    )
    manifest.record_file("extract", "formatted_transcript", formatted)
    manifest.record_file("extract", "clean_text", clean)


def _format_clean(entries) -> str:
    return " ".join(t for _, t in entries)


def _grade_transcript(source: str) -> str:
    return {
        "youtube-transcript-api": "high",
        "yt-dlp": "high",
        "pytube": "medium",
        "whisper": "medium",
    }.get(source, "low")


def _do_frames(args, out_dir: Path, manifest: Manifest) -> None:
    """Wired in Task 6.3."""
    pass


if __name__ == "__main__":
    sys.exit(main())
