"""4-tier transcript fallback chain.

Tiers:
  1. youtube-transcript-api  (YouTube only, fast, free)
  2. pytube captions          (YouTube only, sometimes works when 1 fails)
  3. yt-dlp captions          (any source w/ captions)
  4. Whisper (Groq/OpenAI)    (any source w/ audio; requires API key)

Lifted from download_transcript.py and extended with the Whisper tier from
vendor/claude_video.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi


@dataclass
class TranscriptResult:
    entries: list[tuple[float, str]]
    source: str  # one of: youtube-transcript-api | pytube | yt-dlp | whisper


# --- helpers re-used from download_transcript.py (parsing) ----------------

def _parse_srt(srt_content: str) -> list[tuple[float, str]]:
    entries = []
    for block in re.split(r"\n\n+", srt_content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", lines[1])
        if not m:
            continue
        h, mi, s, ms = map(int, m.groups())
        ts = h * 3600 + mi * 60 + s + ms / 1000
        text = " ".join(lines[2:]).strip()
        if text:
            entries.append((ts, text))
    return entries


def _parse_vtt(vtt_content: str) -> list[tuple[float, str]]:
    raw = []
    lines = vtt_content.split("\n")
    i = 0
    while i < len(lines) and not re.match(r"^\d{2}:\d{2}", lines[i]):
        i += 1
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->", line)
        if not m:
            m = re.match(r"(\d{2}):(\d{2})\.(\d{3})\s*-->", line)
            if m:
                mi, s, ms = map(int, m.groups())
                ts = mi * 60 + s + ms / 1000
            else:
                i += 1
                continue
        else:
            h, mi, s, ms = map(int, m.groups())
            ts = h * 3600 + mi * 60 + s + ms / 1000
        i += 1
        text_lines = []
        while i < len(lines):
            t = lines[i].strip()
            if not t or re.match(r"^\d{2}:\d{2}", t):
                break
            t = re.sub(r"<[^>]+>", "", t)
            text_lines.append(t)
            i += 1
        text = " ".join(text_lines).strip()
        if text:
            raw.append((ts, text))
    out: list[tuple[float, str]] = []
    for j, (ts, text) in enumerate(raw):
        if j + 1 < len(raw) and raw[j + 1][1].startswith(text):
            continue
        out.append((ts, text))
    return out


# --- tier impls -----------------------------------------------------------

def _fetch_via_transcript_api(video_id: str) -> list[tuple[float, str]]:
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    return [(e.start, e.text) for e in transcript]


def _fetch_via_pytube(video_id: str) -> list[tuple[float, str]]:
    from pytube import YouTube
    yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
    cap = yt.captions.get("en") or yt.captions.get("a.en") or (next(iter(yt.captions.values())) if yt.captions else None)
    if not cap:
        raise RuntimeError("no captions via pytube")
    return _parse_srt(cap.generate_srt_captions())


def _fetch_via_ytdlp(video_id_or_url: str) -> list[tuple[float, str]]:
    url = video_id_or_url if "://" in video_id_or_url else f"https://www.youtube.com/watch?v={video_id_or_url}"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(id)s.%(ext)s")
        cmd = ["yt-dlp", "--write-auto-sub", "--write-sub", "--sub-lang", "en",
               "--sub-format", "vtt", "--skip-download", "-o", out, url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        vtts = [f for f in os.listdir(tmp) if f.endswith(".vtt")]
        if not vtts:
            raise RuntimeError(f"yt-dlp: no subtitle file. stderr={r.stderr}")
        with open(os.path.join(tmp, vtts[0]), "r", encoding="utf-8") as f:
            return _parse_vtt(f.read())


def _fetch_via_whisper(audio_path: str, backend: Optional[str] = None) -> list[tuple[float, str]]:
    """Delegate to vendored claude_video Whisper client.

    The vendored whisper module exposes `transcribe_video(video_path, audio_out,
    backend, api_key)` which internally runs ffmpeg to extract audio. Since we
    already have an audio file, we bypass the extraction step and call the
    internal `_post_whisper` + `_segments_from_response` directly to avoid a
    redundant ffmpeg pass.

    Returns [(start_seconds, text), ...]
    """
    from vendor.claude_video.scripts import whisper as _w  # type: ignore

    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise RuntimeError(f"audio file not found: {audio_path}")

    detected_backend, api_key = _w.load_api_key(preferred=backend)
    resolved_backend = backend or detected_backend

    if not resolved_backend or not api_key:
        raise RuntimeError(
            "No Whisper API key available. Set GROQ_API_KEY (preferred) or OPENAI_API_KEY."
        )

    if resolved_backend == "groq":
        endpoint, model = _w.GROQ_ENDPOINT, _w.GROQ_MODEL
    elif resolved_backend == "openai":
        endpoint, model = _w.OPENAI_ENDPOINT, _w.OPENAI_MODEL
    else:
        raise RuntimeError(f"Unknown whisper backend: {resolved_backend}")

    response = _w._post_whisper(endpoint, api_key, model, audio_file)
    segments = _w._segments_from_response(response)

    if not segments:
        raise RuntimeError("Whisper returned no transcript segments")

    return [(float(seg["start"]), seg["text"]) for seg in segments]


# --- public API -----------------------------------------------------------

def fetch_transcript(
    video_id_or_url: str,
    *,
    allow_whisper: bool = False,
    audio_path: Optional[str] = None,
    whisper_backend: Optional[str] = None,
) -> Optional[TranscriptResult]:
    """Try each tier in order until one succeeds.

    Whisper is opt-in (requires audio_path) so we don't accidentally extract
    audio for every YouTube video that already has captions.
    """
    methods = [
        ("youtube-transcript-api", lambda: _fetch_via_transcript_api(video_id_or_url)),
        ("pytube", lambda: _fetch_via_pytube(video_id_or_url)),
        ("yt-dlp", lambda: _fetch_via_ytdlp(video_id_or_url)),
    ]
    if allow_whisper and audio_path:
        methods.append(("whisper", lambda: _fetch_via_whisper(audio_path, whisper_backend)))
    for name, method in methods:
        try:
            entries = method()
            if entries:
                return TranscriptResult(entries=entries, source=name)
        except Exception as e:  # noqa: BLE001 - fall through chain
            print(f"[transcript] {name} failed: {e}")
            continue
    return None
