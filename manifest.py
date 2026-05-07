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
