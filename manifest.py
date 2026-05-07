"""Artifact manifest and source_id derivation."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs


_YT_ID = re.compile(r"^[\w-]{11}$")


def _extract_youtube_id(s: str) -> Optional[str]:
    if _YT_ID.match(s):
        return s
    parsed = urlparse(s)
    if parsed.netloc in ("youtu.be", "www.youtu.be"):
        candidate = parsed.path.lstrip("/")
        return candidate if _YT_ID.match(candidate) else None
    if parsed.netloc in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            v = parse_qs(parsed.query).get("v", [""])[0]
            return v if _YT_ID.match(v) else None
        if parsed.path.startswith(("/v/", "/embed/")):
            candidate = parsed.path.split("/", 2)[2]
            return candidate if _YT_ID.match(candidate) else None
    return None


def derive_source_id(source: str, start: Optional[float] = None, end: Optional[float] = None) -> str:
    """Stable per-source identifier.

    Rules (spec §7.1):
      - YouTube → yt:<video_id>
      - Local file → local:<sha1(abs_path)[:12]>
      - Other URL → web:<sha1(url)[:12]>
      - If start/end provided → suffix #<start>-<end>
    """
    yt = _extract_youtube_id(source)
    if yt:
        sid = f"yt:{yt}"
    elif os.path.exists(source) or source.startswith("/"):
        abs_path = str(Path(source).resolve())
        sid = "local:" + hashlib.sha1(abs_path.encode()).hexdigest()[:12]
    else:
        sid = "web:" + hashlib.sha1(source.encode()).hexdigest()[:12]
    if start is not None or end is not None:
        s_str = "" if start is None else str(int(start))
        e_str = "" if end is None else str(int(end))
        sid += f"#{s_str}-{e_str}"
    return sid


import datetime
import json
from dataclasses import dataclass

MANIFEST_FILENAME = "artifact_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Manifest:
    """Wraps Generated_Data/<title>/artifact_manifest.json."""
    out_dir: Path
    data: dict

    @classmethod
    def load_or_create(cls, out_dir: Path, *, source_id: str, source_url: str, title: str, duration_seconds: float) -> "Manifest":
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / MANIFEST_FILENAME
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("source_id") != source_id:
                raise ValueError(f"manifest source_id mismatch: stored {data.get('source_id')!r} != {source_id!r}")
            return cls(out_dir, data)
        data = {
            "schema_version": 1,
            "source_id": source_id,
            "source_url": source_url,
            "title": title,
            "duration_seconds": duration_seconds,
            "clip_range": None,
            "extract": None,
            "distill_runs": [],
        }
        return cls(out_dir, data)

    def save(self) -> None:
        path = self.out_dir / MANIFEST_FILENAME
        path.write_text(json.dumps(self.data, indent=2, sort_keys=True))

    def set_extract(self, payload: dict) -> None:
        payload = dict(payload)
        payload.setdefault("completed_at", datetime.datetime.utcnow().isoformat() + "Z")
        self.data["extract"] = payload

    def add_distill_run(self, payload: dict) -> None:
        payload = dict(payload)
        payload.setdefault("completed_at", datetime.datetime.utcnow().isoformat() + "Z")
        self.data["distill_runs"].append(payload)

    def record_file(self, section: str, key: str, path: Path) -> None:
        path = Path(path)
        rel = path.relative_to(self.out_dir) if path.is_absolute() and self.out_dir in path.parents else path
        entry = {"path": str(rel), "sha256": _sha256(path) if path.is_file() else None}
        if path.is_dir():
            entry["frame_count"] = sum(1 for _ in path.iterdir() if _.is_file())
        if section == "extract":
            if self.data["extract"] is None:
                self.data["extract"] = {}
            self.data["extract"].setdefault("files", {})[key] = entry
        else:
            raise ValueError(f"unknown section {section!r}")

    def file_intact(self, section: str, key: str) -> bool:
        entry = (self.data.get(section) or {}).get("files", {}).get(key)
        if not entry:
            return False
        full = self.out_dir / entry["path"]
        if not full.exists():
            return False
        if full.is_file():
            return entry.get("sha256") == _sha256(full)
        if full.is_dir():
            return entry.get("frame_count") == sum(1 for _ in full.iterdir() if _.is_file())
        return False
