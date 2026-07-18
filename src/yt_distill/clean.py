"""Storage management — dry-run by default."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone


def _parse_duration(s: str) -> timedelta:
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    raise ValueError(f"unknown duration {s!r} (use Nd or Nh)")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--delete-video", action="store_true")
    p.add_argument("--delete-frames", action="store_true")
    p.add_argument("--keep-ocr", action="store_true", help="(default behavior; explicit)")
    p.add_argument("--older-than", default=None)
    p.add_argument("--source-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--root", default=".")
    args = p.parse_args(argv)

    root = Path(args.root)
    age_cutoff = None
    if args.older_than:
        age_cutoff = datetime.now(timezone.utc) - _parse_duration(args.older_than)

    targets: list[Path] = []
    if args.delete_video:
        for d in (root / "media_cache").glob("*"):
            for f in d.glob("video.*"):
                if _passes_filter(f, age_cutoff, args.source_id, args.title):
                    targets.append(f)
    if args.delete_frames:
        for d in (root / "Generated_Data").glob("*/frames"):
            if _passes_filter(d, age_cutoff, args.source_id, args.title):
                for f in d.iterdir():
                    targets.append(f)

    print(f"[clean] {'APPLY' if args.apply else 'DRY-RUN'} — {len(targets)} files")
    total = 0
    for t in targets:
        size = t.stat().st_size if t.is_file() else 0
        total += size
        print(f"  {'-' if args.apply else '?'} {t} ({size} B)")
    print(f"[clean] total: {total / 1024 / 1024:.2f} MiB")

    if args.apply:
        for t in targets:
            try:
                t.unlink()
            except Exception as e:
                print(f"  failed to delete {t}: {e}", file=sys.stderr)
    return 0


def _passes_filter(path: Path, age_cutoff, source_id_filter, title_filter) -> bool:
    if title_filter and title_filter not in str(path):
        return False
    # source_id filter requires reading the manifest in the same Generated_Data subdir
    if source_id_filter:
        for parent in [path, *path.parents]:
            man = parent / "artifact_manifest.json"
            if man.is_file():
                try:
                    if json.loads(man.read_text(encoding="utf-8")).get("source_id") != source_id_filter:
                        return False
                except Exception:
                    return False
                break
    if age_cutoff:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if mtime > age_cutoff:
            return False
    return True


if __name__ == "__main__":
    sys.exit(main())
