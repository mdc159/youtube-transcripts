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

from yt_distill.core.manifest import derive_source_id, Manifest
from transcript import fetch_transcript
from frame_ocr import (
    FrameClass,
    FrameRecord,
    classify_frame,
    dedup_code_frames,
    ocr_frame,
    write_ocr_json,
)
from vendor.claude_video.scripts import frames as cv_frames


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
    from yt_distill.core import env_bootstrap
    env_bootstrap.load()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    source_id = derive_source_id(args.source, start=args.start, end=args.end)
    print(f"[extract] source_id={source_id}")

    title, duration_seconds, source_url = _probe_source(args.source, cookies_browser=args.cookies_from_browser)
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

    # Compute and write quality grades
    if (out_dir / "ocr.json").exists():
        from frame_ocr import read_ocr_json, FrameClass
        recs = read_ocr_json(out_dir / "ocr.json")
        mean_conf = (sum(r.ocr_confidence for r in recs) / len(recs)) if recs else None
        non_code = sum(1 for r in recs if r.frame_class != FrameClass.CODE)
    else:
        mean_conf = None
        non_code = 0
    _write_extract_meta(out_dir, manifest, mean_conf, non_code)

    # Drop the cached video unless --keep-video
    if not args.keep_video:
        media_cache = Path("media_cache") / out_dir.name
        if media_cache.exists():
            for f in media_cache.glob("video.*"):
                f.unlink(missing_ok=True)

    manifest.save()
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_source(source: str, cookies_browser: str | None = None) -> tuple[str, float, str]:
    """Return (safe_title, duration_seconds, canonical_url_or_path).

    Local files are detected via Path.exists() FIRST so we don't try to ask
    yt-dlp about them.
    """
    if Path(source).exists():
        title = Path(source).stem
        duration = _ffprobe_duration(source)
        return _safe_title(title), duration, str(Path(source).resolve())

    cmd = ["yt-dlp", "--no-warnings", "--dump-json", source]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp probe failed: {r.stderr}")
    info = _json.loads(r.stdout)
    return (
        _safe_title(info.get("title") or info.get("id") or "video"),
        float(info.get("duration") or 0.0),
        info.get("webpage_url") or source,
    )


def _safe_title(t: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", t).strip()
    safe = re.sub(r"[-\s]+", "_", safe)
    return safe or "video"


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
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {r.stderr}")
    return float(r.stdout.strip() or 0.0)


def _whisper_credentials_available() -> bool:
    """True iff GROQ_API_KEY or OPENAI_API_KEY is reachable for the Whisper tier."""
    from vendor.claude_video.scripts import whisper as _w  # type: ignore

    backend, key = _w.load_api_key()
    return bool(backend and key)


def _ensure_video_downloaded(args, out_dir: Path) -> str:
    """Return an absolute path to the source video, downloading if necessary.

    Centralises the local-vs-remote / cache-reuse logic so both the Whisper
    fallback and the frame-extraction step share the same cached download.
    """
    if Path(args.source).exists():
        return str(Path(args.source).resolve())

    cache_dir = Path("media_cache") / out_dir.name
    if cache_dir.exists():
        existing = sorted(cache_dir.glob("video.*"))
        if existing:
            return str(existing[0].resolve())

    return _download_video(args.source, out_dir, args.cookies_from_browser)


def _extract_audio_for_whisper(video_path: str, dest: Path) -> str:
    """Extract a Whisper-friendly audio track via the vendored ffmpeg helper."""
    from vendor.claude_video.scripts import whisper as _w  # type: ignore

    dest.parent.mkdir(parents=True, exist_ok=True)
    _w.extract_audio(video_path, dest)
    return str(dest.resolve())


def _do_transcript(args, out_dir: Path, manifest: Manifest) -> None:
    """Run the 4-tier chain.

    Tiers 1-3 are tried first (cheap, no download). If they all fail and
    Whisper credentials are present (GROQ_API_KEY / OPENAI_API_KEY) and the
    user did not opt out of frame work (which is the only signal that they
    are willing to pull the video at all), we extract audio from the cached
    video and retry with ``allow_whisper=True``.
    """
    cookies_browser = getattr(args, "cookies_from_browser", None)
    res = fetch_transcript(
        args.source,
        allow_whisper=False,
        cookies_browser=cookies_browser,
    )

    if res is None and not getattr(args, "no_frames", False) and _whisper_credentials_available():
        try:
            video_path = _ensure_video_downloaded(args, out_dir)
            audio_dest = Path("media_cache") / out_dir.name / "audio.mp3"
            audio_path = _extract_audio_for_whisper(video_path, audio_dest)
            print("[transcript] tiers 1-3 failed; falling back to Whisper")
            res = fetch_transcript(
                args.source,
                allow_whisper=True,
                audio_path=audio_path,
                cookies_browser=cookies_browser,
            )
        except Exception as exc:  # noqa: BLE001 - fallback is best-effort
            print(f"[transcript] whisper fallback failed: {exc}")
    elif res is None:
        if not _whisper_credentials_available():
            print(
                "[transcript] all tiers failed. Set GROQ_API_KEY (preferred) "
                "or OPENAI_API_KEY to enable the Whisper fallback, or pass "
                "--cookies-from-browser <chrome|edge|firefox> for caption tiers."
            )

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
    """Extract frames + OCR + classification + dedup. Writes ocr.json + manifest entries."""
    frames_dir = out_dir / "frames"
    ocr_json_path = out_dir / "ocr.json"

    # Idempotency: skip if frames_dir intact, ocr.json present, and not forced.
    if (
        not args.force
        and not args.force_ocr
        and ocr_json_path.exists()
        and manifest.file_intact("extract", "frames_dir")
    ):
        print("[extract] frames+ocr: skipping (already complete)")
        return

    # Resolve video path: local file → cached download → fresh download.
    # Reusing the cache means the Whisper fallback above doesn't force a
    # second yt-dlp pull when frames run next.
    video_path = _ensure_video_downloaded(args, out_dir)

    duration = float(manifest.data.get("duration_seconds") or 0.0)
    print(f"[extract] frames: extracting (duration={duration:.1f}s, max={args.max_frames})")
    paths = _extract_frames_adapter(
        video_path=video_path,
        frames_dir=frames_dir,
        duration=duration,
        max_frames=args.max_frames,
        start=args.start,
        end=args.end,
    )
    print(f"[extract] frames: extracted {len(paths)} frames")

    records: list[FrameRecord] = []
    for fp in paths:
        ts = _extract_ts(Path(fp).name)
        # ocr.json stores paths relative to out_dir for portability (spec §7.2).
        rel_path = str(Path(fp).relative_to(out_dir.resolve()))
        try:
            ocr_res = ocr_frame(fp)
            cls, conf = classify_frame(ocr_res)
            if conf < 0.6:
                cls = FrameClass.OTHER
            records.append(
                FrameRecord(
                    path=rel_path,
                    timestamp_seconds=ts,
                    ocr_text=ocr_res.text,
                    ocr_confidence=ocr_res.mean_confidence,
                    frame_class=cls,
                    class_confidence=conf,
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-frame isolation
            records.append(
                FrameRecord(
                    path=rel_path,
                    timestamp_seconds=ts,
                    ocr_text="",
                    ocr_confidence=0.0,
                    frame_class=FrameClass.OTHER,
                    class_confidence=0.0,
                    ocr_error=str(exc),
                )
            )

    records = dedup_code_frames(records)
    write_ocr_json(
        ocr_json_path,
        video_title=out_dir.name,
        duration_seconds=duration,
        frames=records,
    )

    if manifest.data.get("extract") is None:
        manifest.data["extract"] = {}
    manifest.record_file("extract", "frames_dir", frames_dir)
    manifest.record_file("extract", "ocr_json", ocr_json_path)
    manifest.data["extract"]["frame_budget_used"] = len(records)
    manifest.data["extract"]["ocr_version"] = "rapidocr-1.4"
    manifest.data["extract"]["dedup_version"] = 1


def _extract_frames_adapter(
    *,
    video_path: str,
    frames_dir: Path,
    duration: float,
    max_frames: int | None,
    start: float | None,
    end: float | None,
) -> list[str]:
    """Run vendored frames.extract, then rename outputs to spec format.

    Spec citation regex expects ``frame_NNN_t-MM-SS.jpg`` (3-digit serial,
    MM-SS timestamp). Vendored extract emits ``frame_%04d.jpg`` with no
    timestamp encoded in the filename, so we rename in place after extraction.
    """
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Compute effective duration for fps targeting.
    effective_start = start if start is not None else 0.0
    effective_end = end if end is not None else duration
    effective_duration = max(0.0, effective_end - effective_start) if duration > 0 else duration

    budget = max_frames if max_frames is not None else 100
    focused = (start is not None) or (end is not None)
    if focused:
        fps, _target = cv_frames.auto_fps_focus(effective_duration, max_frames=budget)
    else:
        fps, _target = cv_frames.auto_fps(effective_duration, max_frames=budget)

    raw = cv_frames.extract(
        video_path,
        frames_dir,
        fps=fps,
        max_frames=budget,
        start_seconds=start,
        end_seconds=end,
    )

    if len(raw) > 999:
        raise RuntimeError(
            f"frame count {len(raw)} exceeds 3-digit serial cap; "
            "lower --max-frames or extend the filename format"
        )

    # Rename: frame_0001.jpg -> frame_001_t-MM-SS.jpg (3-digit, MM-SS).
    renamed: list[tuple[float, str]] = []
    for i, item in enumerate(raw, start=1):
        ts = float(item["timestamp_seconds"])
        old = Path(item["path"])
        serial = str(i).zfill(3)
        mm = int(ts) // 60
        ss = int(ts) % 60
        if mm > 99:
            raise RuntimeError(
                f"timestamp {ts}s exceeds MM-SS filename format; "
                "videos longer than 99 minutes need a wider format"
            )
        new_name = f"frame_{serial}_t-{mm:02d}-{ss:02d}.jpg"
        new_path = old.parent / new_name
        if old.resolve() != new_path.resolve():
            old.rename(new_path)
        renamed.append((ts, str(new_path.resolve())))

    renamed.sort(key=lambda x: x[0])
    return [p for _, p in renamed]


_TS_RE = re.compile(r"frame_\d{3}_t-(\d{2})-(\d{2})\.jpg$")


def _extract_ts(filename: str) -> float:
    m = _TS_RE.search(filename)
    if not m:
        return 0.0
    return float(int(m.group(1)) * 60 + int(m.group(2)))


def _download_video(url: str, out_dir: Path, cookies_browser: str | None) -> str:
    """Download a video to media_cache/<title>/video.<ext>. Returns absolute path."""
    title = out_dir.name
    cache_dir = Path("media_cache") / title
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(cache_dir / "video.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "best[ext=mp4]",
        "-o",
        output_template,
        url,
    ]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(_ytdlp_error_message(r.stderr))

    candidates = sorted(cache_dir.glob("video.*"))
    if not candidates:
        raise RuntimeError("yt-dlp: no video file produced")
    return str(candidates[0].resolve())


def _ytdlp_error_message(stderr: str) -> str:
    s = stderr or ""
    lower = s.lower()
    if "sign in" in lower or "age" in lower or "login required" in lower or "cookies" in lower:
        return "yt-dlp: source requires authentication / cookies. Pass --cookies-from-browser firefox (or chrome)."
    if "geo" in lower or "not available in your country" in lower:
        return "yt-dlp: source is geo-blocked in your region."
    if "playlist" in lower:
        return "yt-dlp: URL points to a playlist; pass a single-video URL."
    if "429" in lower or "too many requests" in lower:
        return "yt-dlp: rate-limited (429). Retry later."
    return f"yt-dlp failed:\n{s}"


def _grade_ocr(mean_conf: float | None) -> str:
    if mean_conf is None:
        return "none"
    if mean_conf >= 0.85:
        return "high"
    if mean_conf >= 0.65:
        return "medium"
    return "low"


def _grade_frame_coverage(non_code_frames: int, *, duration_seconds: float) -> str:
    minutes = max(0.5, duration_seconds / 60.0)
    rate = non_code_frames / minutes
    if rate >= 4:
        return "high"
    if rate >= 1:
        return "medium"
    return "low"


def _write_extract_meta(out_dir: Path, manifest: Manifest, mean_ocr_conf: float | None, non_code_count: int) -> None:
    meta = {
        "source_id": manifest.data["source_id"],
        "source_url": manifest.data["source_url"],
        "duration_seconds": manifest.data["duration_seconds"],
        "transcript_source": (manifest.data["extract"] or {}).get("transcript_source"),
        "transcript_quality": (manifest.data["extract"] or {}).get("transcript_quality"),
        "ocr_quality": _grade_ocr(mean_ocr_conf),
        "vision_frame_coverage": _grade_frame_coverage(non_code_count, duration_seconds=manifest.data["duration_seconds"]),
        "frame_budget_used": (manifest.data["extract"] or {}).get("frame_budget_used"),
    }
    (out_dir / "extract_meta.json").write_text(_json.dumps(meta, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
