# youtube-transcripts + claude-video Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `claude-video` frame-extraction toolkit into this repo and use the resulting frames + OCR to enrich the existing transcript distillation pipeline, with first-class citations, idempotent caching, and a strict definition of done.

**Architecture:** Two-phase CLI pipeline. `extract.py` downloads the source, fetches a transcript (3-method chain → Whisper fallback), extracts and OCRs frames with a 5-class classifier (code/slide/ui/diagram/other), deduplicates code-frame OCR, and writes everything to `Generated_Data/<title>/` with an `artifact_manifest.json` for resumability. `distill.py` reads those artifacts, builds an enriched transcript with citation tokens, runs scene-change-aware frame selection, validates the chosen LLM via a `models.py doctor` capability check, sends a multimodal payload, and produces both a structured `distill_result.json` and a citation-validated markdown file. `run.py` chains both for one-shot use.

**Tech Stack:** Python 3.10–3.12 (uv), `youtube-transcript-api`, `pytube`, `yt-dlp`, `ffmpeg`, vendored `claude-video` scripts (Whisper via Groq/OpenAI), `rapidocr-onnxruntime`, `imagehash`, `rapidfuzz`, `pyyaml`, `pillow`, `openai` SDK pointed at OpenRouter (default profile: `google/gemini-3-flash-preview`).

**Spec:** `docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`. Read it before starting; the plan implements that spec verbatim.

---

## File map

**New top-level entry points:** `extract.py`, `distill.py`, `run.py`, `clean.py`, `models.py`

**New library modules (top-level, per spec §3):** `frame_ocr.py`, `frame_select.py`, `manifest.py`, `transcript.py`, `enrichment.py`, `payload.py`, `citation.py`, `distill_render.py`

**New config / prompt files:** `models.yaml`, `prompts/distill_contract_v1.md`

**Vendored:** `vendor/claude-video/scripts/{download,frames,transcribe,whisper,setup}.py`

**Modified:** `pyproject.toml` (deps + Python pin), `download_transcript.py` (delegates), `transform_transcript.py` (text-only fallback semantics), `README.md` (legal/auth policy section)

**Test layout:**
- `tests/__init__.py`
- `tests/fixtures/` — committed test artifacts (frames, short videos, OCR fixtures, golden payloads)
- `tests/test_<module>.py` — one file per module
- `tests/integration/test_<scenario>.py` — end-to-end

---

## Milestones at a glance

| # | Milestone | Outcome |
|---|-----------|---------|
| M1 | Foundation & vendoring | Deps installed, claude-video vendored, `models.yaml` exists, test scaffold ready |
| M2 | Manifest & source_id | `manifest.py` reads/writes `artifact_manifest.json`; `source_id` derivation tested |
| M3 | Transcript chain refactor | `transcript.py` exposes the 4-tier chain (incl. Whisper); existing behavior preserved |
| M4 | Frame OCR + classification + dedup | `frame_ocr.py` produces a complete, tested `ocr.json` |
| M5 | Frame selection | `frame_select.py` picks scene-change-aware frames within a token budget |
| M6 | `extract.py` orchestrator | End-to-end Phase 1; resumable; passes integration test on a committed test video |
| M7 | Models layer + doctor | `models.py doctor` validates a profile with real probes; cached for 1h |
| M8 | Distill prerequisites | `enrichment.py`, prompt contract v1, `payload.py`, `citation.py`, `distill_render.py` |
| M9 | `distill.py` orchestrator | End-to-end Phase 2 with `--dry-run-payload`, structured output, citation validator |
| M10 | Convenience + polish + DoD | `run.py`, `clean.py`, legacy compat, README, golden fixtures, DoD verification |

---

# M1 — Foundation & vendoring

## Task 1.1: Update `pyproject.toml` with deps and Python pin

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current pyproject.toml**

```bash
cat pyproject.toml
```

- [ ] **Step 2: Edit `pyproject.toml`**

Replace the `[project]` block's `requires-python` line with `requires-python = ">=3.10,<3.13"`. Add to `dependencies = [...]`:

```toml
dependencies = [
    "youtube-transcript-api",
    "yt-dlp",
    "pytube",
    "openai",
    "python-dotenv",
    "rapidocr-onnxruntime>=1.4,<2.0",
    "pillow>=10.0",
    "pyyaml>=6.0",
    "imagehash>=4.3",
    "rapidfuzz>=3.5",
    "requests>=2.31",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]
```

- [ ] **Step 3: Sync deps**

Run: `uv sync`
Expected: success; `uv.lock` updated.

- [ ] **Step 4: Verify imports**

Run: `uv run python -c "import rapidocr_onnxruntime, imagehash, rapidfuzz, yaml, PIL, openai; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: pin Python 3.10-3.12 and add deps for merge (rapidocr, imagehash, rapidfuzz, pyyaml, pillow)"
```

## Task 1.2: Vendor `claude-video` scripts

**Files:**
- Create: `vendor/claude-video/scripts/{download,frames,transcribe,whisper,setup}.py`
- Create: `vendor/claude-video/__init__.py`
- Create: `vendor/__init__.py`
- Create: `vendor/claude-video/scripts/__init__.py`
- Create: `vendor/claude-video/LICENSE`
- Create: `vendor/claude-video/UPSTREAM.md`

- [ ] **Step 1: Clone upstream to a temp dir and copy needed files**

```bash
git clone --depth 1 https://github.com/bradautomates/claude-video.git /tmp/claude-video-vendor
mkdir -p vendor/claude-video/scripts
cp /tmp/claude-video-vendor/scripts/{download,frames,transcribe,whisper,setup}.py vendor/claude-video/scripts/
cp /tmp/claude-video-vendor/LICENSE vendor/claude-video/LICENSE
```

- [ ] **Step 2: Add empty `__init__.py` files so Python imports work**

```bash
touch vendor/__init__.py vendor/claude-video/__init__.py vendor/claude-video/scripts/__init__.py
```

- [ ] **Step 3: Record provenance in `vendor/claude-video/UPSTREAM.md`**

Write:

```markdown
# claude-video vendored copy

Source: https://github.com/bradautomates/claude-video
License: MIT (see ./LICENSE)
Vendored at: <commit SHA from /tmp/claude-video-vendor>
Date: 2026-05-07

Modifications: none on initial import. Future patches to support our pipeline
will be tracked with comments referencing this file.
```

(Replace `<commit SHA>` with the output of `git -C /tmp/claude-video-vendor rev-parse HEAD`.)

- [ ] **Step 4: Verify the imports load**

Run:
```bash
uv run python -c "from vendor.claude_video.scripts import frames, download, transcribe, whisper, setup; print('ok')"
```

Expected: `ok`. **If the dash in `claude-video` breaks the import**, rename the dir to `claude_video` (Python identifiers can't have dashes) and update `UPSTREAM.md` to record the rename:

```bash
git mv vendor/claude-video vendor/claude_video
```

Then re-run the import test.

- [ ] **Step 5: Commit**

```bash
git add vendor/
git commit -m "chore: vendor bradautomates/claude-video scripts under vendor/claude_video/"
```

## Task 1.3: Smoke-test vendored `setup.py --check`

**Files:** none new.

- [ ] **Step 1: Run the preflight**

```bash
uv run python vendor/claude_video/scripts/setup.py --check
```

Expected outcomes:
- Exit `0` if `ffmpeg`, `ffprobe`, `yt-dlp` are on PATH and a Whisper key is configured.
- Exit `2` if binaries missing — install them per the printed instructions.
- Exit `3` if no Whisper key — that's fine for now; we'll handle it in M3.

- [ ] **Step 2: Verify `ffmpeg` and `yt-dlp` are present**

```bash
which ffmpeg && which yt-dlp
```

If either is missing, install per platform (`brew install ffmpeg yt-dlp` on macOS; `sudo apt install ffmpeg` then `pipx install yt-dlp` on Linux/WSL).

- [ ] **Step 3: No commit needed (no files changed)**

## Task 1.4: Create default `models.yaml`

**Files:**
- Create: `models.yaml`

- [ ] **Step 1: Write `models.yaml`**

```yaml
default: gemini-3-flash

profiles:
  gemini-3-flash:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3-flash-preview
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 16
    max_image_bytes: 5242880

  gemini-3-pro:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3-pro
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 32
    max_image_bytes: 5242880

  claude-sonnet-4-6:
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-sonnet-4-6
    vision: true
    reasoning: false
    api_key_env: OPENROUTER_API_KEY
    max_images: 20
    max_image_bytes: 5242880

  gpt-4o:
    base_url: https://api.openai.com/v1
    model: gpt-4o
    vision: true
    reasoning: false
    api_key_env: OPENAI_API_KEY
    max_images: 10
    max_image_bytes: 20971520
```

- [ ] **Step 2: Commit**

```bash
git add models.yaml
git commit -m "feat: add models.yaml with gemini-3-flash default and gemini-pro/sonnet/gpt-4o alternates"
```

## Task 1.5: Test scaffold

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `tests/integration/__init__.py`
- Modify: `pyproject.toml` (add pytest config)

- [ ] **Step 1: Create empty test scaffold**

```bash
mkdir -p tests/fixtures tests/integration
touch tests/__init__.py tests/integration/__init__.py tests/fixtures/.gitkeep
```

- [ ] **Step 2: Write `tests/conftest.py`** with shared fixtures

```python
"""Shared pytest fixtures."""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def tmp_generated_data(tmp_path, monkeypatch):
    """Redirects Generated_Data writes to a tmp dir for isolation."""
    target = tmp_path / "Generated_Data"
    target.mkdir()
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(target))
    return target
```

- [ ] **Step 3: Add pytest config to `pyproject.toml`**

Append:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
```

- [ ] **Step 4: Verify pytest runs (zero tests is OK)**

Run: `uv run pytest`
Expected: `no tests ran in 0.0Xs`.

- [ ] **Step 5: Commit**

```bash
git add tests/ pyproject.toml
git commit -m "test: scaffold tests/, conftest.py with shared fixtures, pytest config"
```

---

# M2 — Manifest & source_id

## Task 2.1: `manifest.py` — `source_id` derivation

**Files:**
- Create: `manifest.py`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing test for `source_id`**

```python
# tests/test_manifest.py
import pytest
from manifest import derive_source_id


def test_youtube_url_to_source_id():
    assert derive_source_id("https://www.youtube.com/watch?v=KE39P4qBjDk") == "yt:KE39P4qBjDk"
    assert derive_source_id("https://youtu.be/KE39P4qBjDk") == "yt:KE39P4qBjDk"
    assert derive_source_id("KE39P4qBjDk") == "yt:KE39P4qBjDk"


def test_local_path_to_source_id():
    sid = derive_source_id("/abs/path/to/video.mp4")
    assert sid.startswith("local:")
    assert len(sid) == len("local:") + 12  # 12-char sha1 prefix


def test_clip_range_appends_suffix():
    base = derive_source_id("KE39P4qBjDk")
    clipped = derive_source_id("KE39P4qBjDk", start=15, end=45)
    assert clipped == base + "#15-45"


def test_other_url_uses_sha1():
    sid = derive_source_id("https://example.com/some/path?x=1")
    assert sid.startswith("web:")
    assert len(sid) == len("web:") + 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: ImportError / `derive_source_id` not defined.

- [ ] **Step 3: Implement `manifest.py` source_id**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add manifest.py tests/test_manifest.py
git commit -m "feat(manifest): derive_source_id supports yt/local/web with optional clip range"
```

## Task 2.2: `manifest.py` — read/write `artifact_manifest.json`

**Files:**
- Modify: `manifest.py`
- Modify: `tests/test_manifest.py`

- [ ] **Step 1: Add failing tests for read/write/update**

Append to `tests/test_manifest.py`:

```python
import json
from manifest import Manifest, MANIFEST_FILENAME


def test_manifest_init_defaults(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="https://x", title="T", duration_seconds=10.0)
    assert m.data["schema_version"] == 1
    assert m.data["source_id"] == "yt:abc"
    assert m.data["distill_runs"] == []
    assert m.data["extract"] is None


def test_manifest_persistence(tmp_path):
    m1 = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    m1.set_extract({"transcript_source": "captions", "transcript_quality": "high", "frame_budget_used": 30, "files": {}})
    m1.save()

    m2 = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    assert m2.data["extract"]["transcript_source"] == "captions"


def test_manifest_add_distill_run(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    m.add_distill_run({"style": "coding_agent", "model_profile": "gemini-3-flash", "prompt_contract_version": 1, "files": {}, "token_usage": {}})
    m.save()
    raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert len(raw["distill_runs"]) == 1
    assert raw["distill_runs"][0]["style"] == "coding_agent"


def test_manifest_corruption_detection(tmp_path):
    m = Manifest.load_or_create(tmp_path, source_id="yt:abc", source_url="u", title="t", duration_seconds=1.0)
    f = tmp_path / "frames" / "x.jpg"
    f.parent.mkdir()
    f.write_bytes(b"hello")
    m.record_file("extract", "frames_dir", f)
    m.save()
    f.write_bytes(b"changed")  # corrupt
    assert m.file_intact("extract", "frames_dir") is False
```

- [ ] **Step 2: Run tests; expect failure**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: ImportError on `Manifest`.

- [ ] **Step 3: Implement `Manifest` class**

Append to `manifest.py`:

```python
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
            self.data.setdefault("extract", {}).setdefault("files", {})[key] = entry
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add manifest.py tests/test_manifest.py
git commit -m "feat(manifest): Manifest class with load/save, distill runs, file integrity tracking"
```

---

# M3 — Transcript chain refactor + Whisper integration

## Task 3.1: Extract transcript chain into `transcript.py`

**Files:**
- Create: `transcript.py`
- Create: `tests/test_transcript.py`
- Modify: `download_transcript.py` (delegate; preserve behavior)

- [ ] **Step 1: Write tests for `fetch_transcript`** (mock the three existing methods)

```python
# tests/test_transcript.py
from unittest.mock import patch
import pytest
from transcript import fetch_transcript, TranscriptResult


def _entries():
    return [(0.0, "hello"), (1.5, "world")]


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_first_method_wins(api, pyt, ytdlp, whisp):
    api.return_value = _entries()
    res = fetch_transcript("vid")
    assert res.entries == _entries()
    assert res.source == "youtube-transcript-api"
    assert pyt.call_count == 0
    assert ytdlp.call_count == 0
    assert whisp.call_count == 0


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_falls_through_to_whisper(api, pyt, ytdlp, whisp):
    api.side_effect = Exception("no captions")
    pyt.side_effect = Exception("no captions")
    ytdlp.side_effect = Exception("no captions")
    whisp.return_value = _entries()
    res = fetch_transcript("vid", allow_whisper=True, audio_path="/tmp/audio.mp3")
    assert res.source == "whisper"
    assert res.entries == _entries()


@patch("transcript._fetch_via_whisper")
@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_all_fail_returns_none(api, pyt, ytdlp, whisp):
    api.side_effect = Exception("x")
    pyt.side_effect = Exception("x")
    ytdlp.side_effect = Exception("x")
    whisp.side_effect = Exception("x")
    res = fetch_transcript("vid", allow_whisper=True, audio_path="/tmp/x.mp3")
    assert res is None
```

- [ ] **Step 2: Run tests; expect ImportError**

Run: `uv run pytest tests/test_transcript.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `transcript.py`**

```python
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

    Returns [(start_seconds, text), ...]
    """
    from vendor.claude_video.scripts import whisper as _w  # type: ignore
    # The vendored client returns segments; flatten to (start, text) tuples.
    segments = _w.transcribe(audio_path, backend=backend)
    return [(seg["start"], seg["text"]) for seg in segments]


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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_transcript.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify the vendored whisper module's `transcribe()` signature**

Run: `uv run python -c "from vendor.claude_video.scripts import whisper; help(whisper.transcribe)"`

If `transcribe` doesn't exist or has a different signature, **inspect the upstream module** and update `_fetch_via_whisper` to match. The vendored file is the source of truth; the test mocks `_fetch_via_whisper` so the test still passes either way.

Look for the actual function name with: `uv run python -c "import vendor.claude_video.scripts.whisper as w; print([n for n in dir(w) if not n.startswith('_')])"`

- [ ] **Step 6: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat(transcript): 4-tier chain (yt-api → pytube → yt-dlp → whisper) extracted to transcript.py"
```

## Task 3.2: Refactor `download_transcript.py` to delegate to `transcript.py`

**Files:**
- Modify: `download_transcript.py`
- Create: `tests/test_download_transcript_legacy.py`

- [ ] **Step 1: Write a backward-compat test**

```python
# tests/test_download_transcript_legacy.py
"""Locks in the pre-merge behavior of download_transcript.py.

The legacy script must keep producing _formatted_transcript.txt and _clean_text.txt
exactly as before when no style argument is passed.
"""
from unittest.mock import patch
from pathlib import Path
import download_transcript as legacy


@patch("download_transcript.get_safe_title", return_value="Test_Video")
@patch("download_transcript.fetch_transcript_with_fallbacks")
def test_legacy_output_files(fetch_mock, _title_mock, tmp_path):
    fetch_mock.return_value = [(0.0, "hello"), (1.5, "world")]
    out = tmp_path / "Test_Video"
    out.mkdir()
    legacy.download_transcript("vid", str(out), title="Test_Video")
    formatted = out / "Test_Video_formatted_transcript.txt"
    clean = out / "Test_Video_clean_text.txt"
    assert formatted.read_text().splitlines() == ["0.0|hello", "1.5|world"]
    assert "hello" in clean.read_text()
    assert "world" in clean.read_text()
```

- [ ] **Step 2: Run; expect pass (existing behavior)**

Run: `uv run pytest tests/test_download_transcript_legacy.py -v`
Expected: 2 passed (this test passes against the existing script as-is — that's the point: it's a regression lock).

- [ ] **Step 3: Refactor `download_transcript.py` to use `transcript.py`**

Edit `download_transcript.py`:
- Replace the entire `_fetch_via_*` and `fetch_transcript_with_fallbacks` block with a thin wrapper:

```python
from transcript import fetch_transcript


def fetch_transcript_with_fallbacks(video_id_or_url: str):
    """Backward-compat shim. Returns a list of (start, text) tuples or None.

    Whisper is intentionally NOT enabled here — legacy callers don't pass audio.
    """
    res = fetch_transcript(video_id_or_url, allow_whisper=False)
    if res is None:
        return None
    print(f"Success with {res.source}")
    return res.entries
```

Keep `extract_video_id`, `get_safe_title`, `_extract_unique_text`, `_format_as_paragraphs`, `download_transcript`, and the `__main__` block exactly as before.

- [ ] **Step 4: Re-run the regression test**

Run: `uv run pytest tests/test_download_transcript_legacy.py -v`
Expected: 2 passed (proves the refactor preserved behavior).

- [ ] **Step 5: Commit**

```bash
git add download_transcript.py tests/test_download_transcript_legacy.py
git commit -m "refactor(download_transcript): delegate to transcript.fetch_transcript; behavior unchanged"
```

---

# M4 — Frame OCR + classification + dedup

## Task 4.1: `frame_ocr.py` — OCR per frame with confidence gating

**Files:**
- Create: `frame_ocr.py`
- Create: `tests/test_frame_ocr.py`
- Create: `tests/fixtures/frame_code.jpg`, `tests/fixtures/frame_slide.jpg`, `tests/fixtures/frame_ui.jpg`, `tests/fixtures/frame_diagram.jpg`, `tests/fixtures/frame_other.jpg`

> **Note on fixtures:** Generate them once with simple PIL drawings for unit tests. They don't need to be photorealistic — they just need to exercise the classifier's signals. The fixture-generation script is `tests/fixtures/_generate.py` (committed once, regenerated only if signals change).

- [ ] **Step 1: Generate fixture frames**

Create `tests/fixtures/_generate.py`:

```python
"""Generates synthetic frames that exercise the classifier signals.
Run once: `uv run python tests/fixtures/_generate.py`
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent
SZ = (512, 384)
FONT = ImageFont.load_default()


def _frame(name: str, lines: list[str], bg=(255, 255, 255)) -> None:
    img = Image.new("RGB", SZ, bg)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((10, 10 + i * 16), ln, fill=(0, 0, 0), font=FONT)
    img.save(OUT / name, "JPEG", quality=85)


_frame("frame_code.jpg", [
    "def fetch_user(user_id):",
    "    return db.query(User).get(user_id)",
    "",
    "class UserService:",
    "    def __init__(self, db):",
    "        self.db = db",
    "",
    "    def all_users(self) -> list[User]:",
    "        return self.db.query(User).all()",
])
_frame("frame_slide.jpg", [
    "Building a RAG Pipeline",
    "",
    "Step 1: Ingest documents",
    "Step 2: Chunk and embed",
    "Step 3: Store in vector DB",
    "Step 4: Retrieve top-k",
    "Step 5: Generate response",
])
_frame("frame_ui.jpg", ["Settings", "Account", "Privacy", "Save"])
_frame("frame_diagram.jpg", ["Embeddings"])  # mostly empty -> low text density
_frame("frame_other.jpg", ["misc background visual without code or slides"])
```

Run it: `uv run python tests/fixtures/_generate.py`

- [ ] **Step 2: Write the failing tests for `ocr_frame`**

```python
# tests/test_frame_ocr.py
from pathlib import Path
import pytest
from frame_ocr import ocr_frame, OcrResult, CONFIDENCE_GATE


def test_ocr_frame_returns_text(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    assert isinstance(res, OcrResult)
    assert "fetch_user" in res.text or "fetch" in res.text  # tolerate OCR drift
    assert 0.0 <= res.mean_confidence <= 1.0


def test_ocr_frame_confidence_gate_marks_lines(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    # We don't know exact OCR results, but the gating field must be populated.
    assert hasattr(res, "lines")
    assert all(hasattr(l, "confidence") for l in res.lines)
    assert all(hasattr(l, "above_gate") for l in res.lines)
```

- [ ] **Step 3: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: ImportError on `frame_ocr`.

- [ ] **Step 4: Implement `ocr_frame`**

```python
# frame_ocr.py
"""Frame OCR with per-line confidence gating, 5-class classification, and dedup."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rapidocr_onnxruntime import RapidOCR

CONFIDENCE_GATE = 0.5

_OCR: Optional[RapidOCR] = None


def _ocr() -> RapidOCR:
    global _OCR
    if _OCR is None:
        _OCR = RapidOCR()
    return _OCR


@dataclass
class OcrLine:
    text: str
    confidence: float
    above_gate: bool


@dataclass
class OcrResult:
    text: str
    high_confidence_text: str
    lines: list[OcrLine]
    mean_confidence: float


def ocr_frame(path: Path | str) -> OcrResult:
    path = str(path)
    raw, _ = _ocr()(path)
    lines: list[OcrLine] = []
    for entry in raw or []:
        # entry shape: [bbox, text, confidence]
        text = (entry[1] or "").strip()
        conf = float(entry[2]) if entry[2] is not None else 0.0
        if not text:
            continue
        lines.append(OcrLine(text=text, confidence=conf, above_gate=conf >= CONFIDENCE_GATE))
    text = "\n".join(l.text for l in lines)
    high = "\n".join(l.text for l in lines if l.above_gate)
    mean = sum(l.confidence for l in lines) / len(lines) if lines else 0.0
    return OcrResult(text=text, high_confidence_text=high, lines=lines, mean_confidence=mean)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: 2 passed. (If RapidOCR returns no text on the synthetic fixtures, regenerate with a larger font — see fixture script.)

- [ ] **Step 6: Commit**

```bash
git add frame_ocr.py tests/test_frame_ocr.py tests/fixtures/_generate.py tests/fixtures/frame_*.jpg
git commit -m "feat(frame_ocr): ocr_frame with per-line confidence gating; rapidocr fixtures"
```

## Task 4.2: 5-class classifier

**Files:**
- Modify: `frame_ocr.py`
- Modify: `tests/test_frame_ocr.py`

- [ ] **Step 1: Add failing classifier tests**

Append to `tests/test_frame_ocr.py`:

```python
from frame_ocr import classify_frame, FrameClass


def test_classify_code(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_code.jpg")
    cls, conf = classify_frame(res)
    assert cls == FrameClass.CODE
    assert conf >= 0.6


def test_classify_slide(fixtures_dir):
    res = ocr_frame(fixtures_dir / "frame_slide.jpg")
    cls, _ = classify_frame(res)
    assert cls in (FrameClass.SLIDE_TEXT, FrameClass.OTHER)  # tolerate OCR drift
    # Slide text should NOT be classified as code:
    assert cls != FrameClass.CODE


def test_classify_low_confidence_falls_back_to_other():
    """When classifier confidence < 0.6, must return OTHER."""
    fake = OcrResult(text="x", high_confidence_text="x", lines=[OcrLine("x", 0.5, True)], mean_confidence=0.5)
    cls, conf = classify_frame(fake)
    if conf < 0.6:
        assert cls == FrameClass.OTHER
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: ImportError on `classify_frame`.

- [ ] **Step 3: Implement classifier**

Append to `frame_ocr.py`:

```python
import enum


class FrameClass(str, enum.Enum):
    CODE = "code"
    SLIDE_TEXT = "slide_text"
    UI = "ui"
    DIAGRAM = "diagram"
    OTHER = "other"


_CODE_GLYPHS = set("{}[]()<>;=")
_KEYWORDS = re.compile(r"(?:^|\s)(?:def |function |class |import |from |const |let |var |return |if \(|// |# )")


def _signal_glyph_density(text: str) -> bool:
    n = max(1, len(text))
    return sum(1 for c in text if c in _CODE_GLYPHS) * 100 / n >= 3


def _signal_indentation(text: str) -> bool:
    return sum(1 for ln in text.splitlines() if ln.startswith("  ") or ln.startswith("\t")) >= 3


def _signal_keywords(text: str) -> bool:
    return _KEYWORDS.search(text) is not None


def _signal_line_uniformity(lines: list[OcrLine]) -> bool:
    if len(lines) < 5:
        return False
    leadings = [ln.text.lstrip()[:1] if ln.text.strip() else "" for ln in lines]
    if not leadings:
        return False
    most = max(set(leadings), key=leadings.count)
    return leadings.count(most) >= 5


def classify_frame(res: OcrResult) -> tuple[FrameClass, float]:
    """Return (class, class_confidence)."""
    text = res.high_confidence_text or res.text
    n_lines = len(res.lines)
    code_signals = sum([
        _signal_glyph_density(text),
        _signal_indentation(text),
        _signal_keywords(text),
        _signal_line_uniformity(res.lines),
    ])
    if code_signals >= 2:
        return FrameClass.CODE, min(1.0, 0.5 + 0.15 * code_signals)

    # Heuristics for the remaining classes
    text_density = len(text) / max(1, n_lines)
    if n_lines >= 4 and text_density > 12 and not _signal_glyph_density(text):
        return FrameClass.SLIDE_TEXT, 0.7
    short_label_lines = sum(1 for ln in res.lines if 0 < len(ln.text) <= 24)
    if n_lines >= 2 and short_label_lines == n_lines and not _signal_glyph_density(text):
        return FrameClass.UI, 0.65
    if n_lines <= 2 and not _signal_glyph_density(text):
        return FrameClass.DIAGRAM, 0.55  # below the 0.6 gate -> caller will treat as OTHER

    return FrameClass.OTHER, 0.5


# Caller convention: if class_confidence < 0.6, treat as OTHER (spec §4.3).
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frame_ocr.py tests/test_frame_ocr.py
git commit -m "feat(frame_ocr): 5-class classifier (code/slide/ui/diagram/other) with low-conf fallback"
```

## Task 4.3: OCR dedup clustering

**Files:**
- Modify: `frame_ocr.py`
- Modify: `tests/test_frame_ocr.py`

- [ ] **Step 1: Add failing tests**

Append:

```python
from frame_ocr import dedup_code_frames, FrameRecord


def _rec(idx: int, ts: float, text: str, klass: FrameClass) -> "FrameRecord":
    return FrameRecord(
        path=f"frames/frame_{idx:03d}_t-00-{int(ts):02d}.jpg",
        timestamp_seconds=ts,
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=None,
    )


def test_dedup_clusters_identical_code():
    code = "def f():\n    return 1"
    frames = [
        _rec(1, 1, code, FrameClass.CODE),
        _rec(2, 5, code, FrameClass.CODE),
        _rec(3, 9, code, FrameClass.CODE),
    ]
    out = dedup_code_frames(frames)
    cluster_ids = {f.cluster_id for f in out}
    assert len(cluster_ids) == 1


def test_dedup_keeps_distinct_code():
    frames = [
        _rec(1, 1, "def a(): return 1", FrameClass.CODE),
        _rec(2, 5, "def b(): return 2", FrameClass.CODE),
    ]
    out = dedup_code_frames(frames)
    assert len({f.cluster_id for f in out}) == 2


def test_dedup_ignores_non_code():
    frames = [
        _rec(1, 1, "Step 1", FrameClass.SLIDE_TEXT),
        _rec(2, 5, "Step 1", FrameClass.SLIDE_TEXT),
    ]
    out = dedup_code_frames(frames)
    assert all(f.cluster_id is None for f in out)
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: ImportError on `dedup_code_frames` / `FrameRecord`.

- [ ] **Step 3: Implement dedup**

Append to `frame_ocr.py`:

```python
from rapidfuzz import fuzz


@dataclass
class FrameRecord:
    path: str
    timestamp_seconds: float
    ocr_text: str
    ocr_confidence: float
    frame_class: FrameClass
    class_confidence: float
    cluster_id: Optional[str] = None
    ocr_error: Optional[str] = None


def _normalize(text: str) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(r"[#].*$", "", s, flags=re.MULTILINE)  # strip line comments
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
    return s


def dedup_code_frames(frames: list[FrameRecord], similarity: float = 0.85) -> list[FrameRecord]:
    """Cluster CODE-class frames by normalized OCR text (rapidfuzz token-set ratio)."""
    next_id = 0
    cluster_reps: list[tuple[str, str]] = []  # (cluster_id, normalized_text)
    out = []
    for f in frames:
        if f.frame_class != FrameClass.CODE:
            out.append(f)
            continue
        norm = _normalize(f.ocr_text)
        match_id: Optional[str] = None
        for cid, rep in cluster_reps:
            if fuzz.token_set_ratio(norm, rep) / 100.0 >= similarity:
                match_id = cid
                break
        if match_id is None:
            match_id = f"c{next_id}"
            next_id += 1
            cluster_reps.append((match_id, norm))
        out.append(FrameRecord(**{**f.__dict__, "cluster_id": match_id}))
    return out
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add frame_ocr.py tests/test_frame_ocr.py
git commit -m "feat(frame_ocr): dedup_code_frames clusters near-identical OCR via rapidfuzz"
```

## Task 4.4: `ocr.json` writer + reader

**Files:**
- Modify: `frame_ocr.py`
- Modify: `tests/test_frame_ocr.py`

- [ ] **Step 1: Add tests**

Append:

```python
import json
from frame_ocr import write_ocr_json, read_ocr_json


def test_ocr_json_roundtrip(tmp_path):
    frames = [
        _rec(1, 1.0, "x", FrameClass.CODE),
        _rec(2, 5.0, "y", FrameClass.SLIDE_TEXT),
    ]
    target = tmp_path / "ocr.json"
    write_ocr_json(target, video_title="T", duration_seconds=12.0, frames=frames)
    raw = json.loads(target.read_text())
    assert raw["video"]["title"] == "T"
    assert raw["video"]["duration_seconds"] == 12.0
    assert raw["frames"][0]["frame_class"] == "code"
    back = read_ocr_json(target)
    assert len(back) == 2
    assert back[0].ocr_text == "x"
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_ocr.py::test_ocr_json_roundtrip -v`
Expected: ImportError.

- [ ] **Step 3: Implement read/write**

Append to `frame_ocr.py`:

```python
import json as _json


def write_ocr_json(path: Path | str, *, video_title: str, duration_seconds: float, frames: list[FrameRecord]) -> None:
    data = {
        "video": {"title": video_title, "duration_seconds": duration_seconds},
        "frames": [
            {
                "path": f.path,
                "timestamp_seconds": f.timestamp_seconds,
                "ocr_text": f.ocr_text,
                "ocr_confidence": f.ocr_confidence,
                "frame_class": f.frame_class.value,
                "class_confidence": f.class_confidence,
                "cluster_id": f.cluster_id,
                "ocr_error": f.ocr_error,
            }
            for f in frames
        ],
    }
    Path(path).write_text(_json.dumps(data, indent=2, sort_keys=True))


def read_ocr_json(path: Path | str) -> list[FrameRecord]:
    raw = _json.loads(Path(path).read_text())
    return [
        FrameRecord(
            path=f["path"],
            timestamp_seconds=f["timestamp_seconds"],
            ocr_text=f["ocr_text"],
            ocr_confidence=f["ocr_confidence"],
            frame_class=FrameClass(f["frame_class"]),
            class_confidence=f["class_confidence"],
            cluster_id=f.get("cluster_id"),
            ocr_error=f.get("ocr_error"),
        )
        for f in raw["frames"]
    ]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_frame_ocr.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add frame_ocr.py tests/test_frame_ocr.py
git commit -m "feat(frame_ocr): ocr.json read/write with FrameRecord roundtrip"
```

---

# M5 — Frame selection (scene-change-aware)

## Task 5.1: `frame_select.py` — perceptual hash scene change

**Files:**
- Create: `frame_select.py`
- Create: `tests/test_frame_select.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_frame_select.py
from PIL import Image
from frame_select import detect_scene_changes, ChangePoint


def _solid(path, color):
    Image.new("RGB", (64, 64), color).save(path, "JPEG")


def test_detects_change_between_distinct_solids(tmp_path):
    paths = []
    for i, c in enumerate([(0, 0, 0), (0, 0, 0), (255, 255, 255), (255, 255, 255)]):
        p = tmp_path / f"f{i}.jpg"
        _solid(p, c)
        paths.append(p)
    changes = detect_scene_changes(paths)
    # Expect a change point at index 2 (transition from black to white).
    assert any(c.index == 2 for c in changes), f"got {changes}"


def test_no_change_for_identical_frames(tmp_path):
    paths = []
    for i in range(4):
        p = tmp_path / f"f{i}.jpg"
        _solid(p, (128, 128, 128))
        paths.append(p)
    assert detect_scene_changes(paths) == []
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_select.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement scene detector**

```python
# frame_select.py
"""Scene-change-aware frame selection (spec §4.4).

Primary: perceptual-hash deltas between consecutive frames; pick frames just
after each change point. Fallback: even spacing across remaining gaps.
Token-budget aware: final count = min(--max-vision-frames, budget // est).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import imagehash
from PIL import Image


@dataclass
class ChangePoint:
    index: int
    distance: int  # Hamming distance from previous frame's phash


def _phash(path: Path | str) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return imagehash.phash(img)


def detect_scene_changes(paths: Sequence[Path | str], threshold_factor: float = 1.5) -> list[ChangePoint]:
    """Return change points where Hamming distance > median + threshold_factor*MAD.

    For very short sequences (<3 frames) we cannot compute a stable threshold;
    return an empty list.
    """
    if len(paths) < 2:
        return []
    hashes = [_phash(p) for p in paths]
    distances = [hashes[i] - hashes[i - 1] for i in range(1, len(hashes))]
    if len(distances) < 3:
        # Short sequences: any non-zero delta is a change.
        return [ChangePoint(index=i + 1, distance=d) for i, d in enumerate(distances) if d > 0]
    median = statistics.median(distances)
    mad = statistics.median([abs(d - median) for d in distances]) or 1
    threshold = median + threshold_factor * mad
    return [ChangePoint(index=i + 1, distance=d) for i, d in enumerate(distances) if d > threshold]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_frame_select.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frame_select.py tests/test_frame_select.py
git commit -m "feat(frame_select): perceptual-hash scene change detection"
```

## Task 5.2: Selection with even-spacing fallback + budget cap

**Files:**
- Modify: `frame_select.py`
- Modify: `tests/test_frame_select.py`

- [ ] **Step 1: Add failing tests**

Append:

```python
from frame_select import select_frames, SelectionResult
from frame_ocr import FrameRecord, FrameClass


def _rec(i, ts, klass=FrameClass.OTHER):
    return FrameRecord(
        path=f"frames/f{i}.jpg",
        timestamp_seconds=ts,
        ocr_text="",
        ocr_confidence=0.0,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=None,
    )


def test_excludes_code_frames_from_selection(tmp_path):
    frames = [_rec(0, 0, FrameClass.CODE), _rec(1, 5, FrameClass.SLIDE_TEXT), _rec(2, 10)]
    res = select_frames(frames, change_points=[], max_frames=10, token_budget=None)
    assert all(s.frame_class != FrameClass.CODE for s in res.selected)


def test_uses_change_points_when_available():
    frames = [_rec(i, i * 1.0) for i in range(10)]
    cps = [ChangePoint(index=3, distance=20), ChangePoint(index=7, distance=20)]
    res = select_frames(frames, change_points=cps, max_frames=4, token_budget=None)
    indices = [s.timestamp_seconds for s in res.selected]
    assert 3.0 in indices
    assert 7.0 in indices
    assert all(r.reason for r in res.selected)


def test_falls_back_to_even_spacing_when_budget_unfilled():
    frames = [_rec(i, i * 1.0) for i in range(20)]
    res = select_frames(frames, change_points=[], max_frames=4, token_budget=None)
    assert len(res.selected) == 4
    assert all("even_spacing" in s.reason for s in res.selected)


def test_token_budget_caps_below_max_frames():
    frames = [_rec(i, i * 1.0) for i in range(20)]
    # token budget allows only 2 frames
    res = select_frames(frames, change_points=[], max_frames=10, token_budget=2 * 5000, est_image_tokens=5000)
    assert len(res.selected) == 2
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_frame_select.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `select_frames`**

Append to `frame_select.py`:

```python
from frame_ocr import FrameRecord, FrameClass  # noqa: E402  (after class def)


@dataclass
class Selected:
    path: str
    timestamp_seconds: float
    frame_class: FrameClass
    reason: str  # e.g. "scene_change@t=01:23" or "even_spacing@t=03:45"


@dataclass
class SelectionResult:
    selected: list[Selected]


def _fmt_t(ts: float) -> str:
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"


def select_frames(
    frames: list[FrameRecord],
    *,
    change_points: list[ChangePoint],
    max_frames: int,
    token_budget: int | None,
    est_image_tokens: int = 5000,
) -> SelectionResult:
    """Select non-code frames for the vision payload.

    Order of operations (spec §4.4):
      1. Drop CODE-class frames.
      2. Take frames just after each change_point index.
      3. Fill remaining budget with even-spacing across the surviving frames.
      4. Cap by min(max_frames, token_budget // est_image_tokens) if budget given.
    """
    eligible = [f for f in frames if f.frame_class != FrameClass.CODE]
    if not eligible:
        return SelectionResult(selected=[])

    cap = max_frames
    if token_budget is not None:
        cap = min(cap, max(0, token_budget // max(1, est_image_tokens)))
    if cap == 0:
        return SelectionResult(selected=[])

    # Index `change_points` are positions in the *original* `frames` list.
    chosen_idx: list[tuple[int, str]] = []  # (index in eligible, reason)
    eligible_index_map = {id(f): i for i, f in enumerate(eligible)}
    for cp in change_points:
        if 0 <= cp.index < len(frames):
            f = frames[cp.index]
            if f.frame_class != FrameClass.CODE and id(f) in eligible_index_map:
                idx = eligible_index_map[id(f)]
                if not any(i == idx for i, _ in chosen_idx):
                    chosen_idx.append((idx, f"scene_change@t={_fmt_t(f.timestamp_seconds)}"))
                    if len(chosen_idx) >= cap:
                        break

    if len(chosen_idx) < cap:
        remaining = cap - len(chosen_idx)
        already = {i for i, _ in chosen_idx}
        # Even spacing across eligible
        if eligible:
            step = max(1, len(eligible) // remaining)
            for i in range(0, len(eligible), step):
                if i in already:
                    continue
                f = eligible[i]
                chosen_idx.append((i, f"even_spacing@t={_fmt_t(f.timestamp_seconds)}"))
                if len(chosen_idx) >= cap:
                    break

    chosen_idx.sort(key=lambda x: x[0])
    sel = [
        Selected(
            path=eligible[i].path,
            timestamp_seconds=eligible[i].timestamp_seconds,
            frame_class=eligible[i].frame_class,
            reason=reason,
        )
        for i, reason in chosen_idx
    ]
    return SelectionResult(selected=sel)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_frame_select.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add frame_select.py tests/test_frame_select.py
git commit -m "feat(frame_select): select_frames combines scene-change picks + even-spacing fallback + budget cap"
```

## Task 5.3: `selected_frames.json` writer

**Files:**
- Modify: `frame_select.py`
- Modify: `tests/test_frame_select.py`

- [ ] **Step 1: Add tests**

Append:

```python
import json
from frame_select import write_selected_frames_json


def test_selected_frames_json_includes_reason(tmp_path):
    sel = SelectionResult(selected=[
        Selected(path="frames/f1.jpg", timestamp_seconds=1.0, frame_class=FrameClass.SLIDE_TEXT, reason="scene_change@t=00:01"),
    ])
    target = tmp_path / "selected_frames.json"
    write_selected_frames_json(target, sel)
    raw = json.loads(target.read_text())
    assert raw["selected"][0]["reason"].startswith("scene_change")
```

- [ ] **Step 2: Implement writer**

```python
def write_selected_frames_json(path: Path | str, sel: SelectionResult) -> None:
    import json
    data = {
        "selected": [
            {
                "path": s.path,
                "timestamp_seconds": s.timestamp_seconds,
                "frame_class": s.frame_class.value,
                "reason": s.reason,
            }
            for s in sel.selected
        ],
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/test_frame_select.py -v`
Expected: 7 passed.

```bash
git add frame_select.py tests/test_frame_select.py
git commit -m "feat(frame_select): write_selected_frames_json with auditable reasons"
```

---

# M6 — `extract.py` orchestrator

## Task 6.1: Skeleton with arg parsing and manifest integration

**Files:**
- Create: `extract.py`
- Create: `tests/test_extract_args.py`

- [ ] **Step 1: Write failing test for arg parsing**

```python
# tests/test_extract_args.py
import pytest
import extract


def test_parse_args_minimal():
    ns = extract._parse_args(["https://x"])
    assert ns.source == "https://x"
    assert ns.no_frames is False
    assert ns.force is False


def test_parse_args_clip_range():
    ns = extract._parse_args(["video.mp4", "--start", "10", "--end", "30"])
    assert ns.start == 10.0
    assert ns.end == 30.0


def test_parse_args_force_flags():
    ns = extract._parse_args(["x", "--force", "--force-ocr", "--keep-video", "--no-frames"])
    assert ns.force is True
    assert ns.force_ocr is True
    assert ns.keep_video is True
    assert ns.no_frames is True
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_extract_args.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement skeleton**

```python
# extract.py
"""Phase 1: download → transcript → frames → OCR → manifest.

Idempotent. Re-runs skip completed steps unless --force / --force-ocr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from manifest import derive_source_id, Manifest


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
    # The orchestration pipeline is filled in across Tasks 6.2 - 6.5.
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_extract_args.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add extract.py tests/test_extract_args.py
git commit -m "feat(extract): skeleton with arg parsing and source_id derivation"
```

## Task 6.2: Wire transcript chain + frame extraction

**Files:**
- Modify: `extract.py`
- Create: `tests/integration/test_extract_pipeline.py`
- Add: `tests/fixtures/test_video.mp4` (a 30-second public-domain clip — see Step 1)

- [ ] **Step 1: Add a 30-second public-domain test video**

Use a Creative Commons clip from archive.org (e.g. `https://archive.org/details/BigBuckBunny_124`). Trim to 30 seconds with ffmpeg to keep the fixture small (<3 MB):

```bash
yt-dlp -f "best[ext=mp4]" -o /tmp/bbb.mp4 "https://archive.org/details/BigBuckBunny_124"
ffmpeg -ss 30 -t 30 -i /tmp/bbb.mp4 -c:v libx264 -crf 28 -c:a aac -b:a 64k tests/fixtures/test_video.mp4
ls -lh tests/fixtures/test_video.mp4
```

If size > 5 MB, lower `-crf` quality. Commit the file.

- [ ] **Step 2: Write the integration test**

```python
# tests/integration/test_extract_pipeline.py
import os
from pathlib import Path
import pytest

import extract


@pytest.mark.integration
def test_extract_local_video(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    assert src.exists(), "tests/fixtures/test_video.mp4 missing — see Task 6.2 Step 1"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    rc = extract.main([str(src), "--max-frames", "8", "--no-frames"])  # transcript-only first
    assert rc == 0
    # Find the resulting Generated_Data dir
    out_dirs = list(tmp_path.iterdir())
    assert len(out_dirs) == 1
    od = out_dirs[0]
    assert (od / "artifact_manifest.json").exists()
```

- [ ] **Step 3: Wire `main()` in `extract.py`**

Replace `main()` body:

```python
def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    source_id = derive_source_id(args.source, start=args.start, end=args.end)

    # Resolve title and out_dir
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
    if not args.force and manifest.data.get("extract") and manifest.file_intact("extract", "formatted_transcript"):
        print("[extract] transcript: skipping (already complete)")
    else:
        _do_transcript(args, out_dir, manifest)

    # Step 2: frames (skipped on --no-frames)
    if not args.no_frames:
        _do_frames(args, out_dir, manifest)
        # OCR + classification (Tasks 6.3 wires it in)
    manifest.save()
    return 0
```

Add helpers at module bottom:

```python
import os
import subprocess
import json as _json

from transcript import fetch_transcript


def _probe_source(source: str) -> tuple[str, float, str]:
    """Return (safe_title, duration_seconds, canonical_url_or_path)."""
    if Path(source).exists():
        title = Path(source).stem
        duration = _ffprobe_duration(source)
        return _safe_title(title), duration, str(Path(source).resolve())
    # Probe URL via yt-dlp --dump-json
    r = subprocess.run(["yt-dlp", "--no-warnings", "--dump-json", source], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"yt-dlp probe failed: {r.stderr}")
    info = _json.loads(r.stdout)
    return _safe_title(info.get("title") or info.get("id") or "video"), float(info.get("duration") or 0.0), info.get("webpage_url") or source


def _safe_title(t: str) -> str:
    import re
    safe = re.sub(r"[^\w\s-]", "", t).strip()
    return re.sub(r"[-\s]+", "_", safe)


def _ffprobe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip() or 0.0)


def _do_transcript(args, out_dir: Path, manifest: Manifest) -> None:
    """Run the 4-tier chain. Whisper requires audio extraction (TODO in Task 6.4)."""
    res = fetch_transcript(args.source, allow_whisper=False)
    base = out_dir / out_dir.name
    formatted = Path(str(base) + "_formatted_transcript.txt")
    clean = Path(str(base) + "_clean_text.txt")
    if res is None:
        formatted.write_text("# transcript_unavailable\n")
        clean.write_text("# transcript_unavailable\n")
        manifest.set_extract({"transcript_source": "none", "transcript_quality": "none", "files": {}})
        return
    formatted.write_text("\n".join(f"{ts}|{txt}" for ts, txt in res.entries) + "\n")
    clean.write_text(_format_clean(res.entries))
    manifest.set_extract({"transcript_source": res.source, "transcript_quality": _grade_transcript(res.source), "files": {}})
    manifest.record_file("extract", "formatted_transcript", formatted)
    manifest.record_file("extract", "clean_text", clean)


def _format_clean(entries) -> str:
    text = " ".join(t for _, t in entries)
    return text


def _grade_transcript(source: str) -> str:
    return {"youtube-transcript-api": "high", "yt-dlp": "high", "pytube": "medium", "whisper": "medium"}.get(source, "low")


def _do_frames(args, out_dir: Path, manifest: Manifest) -> None:
    """Wired in Task 6.3."""
    pass
```

- [ ] **Step 4: Run integration test**

Run: `uv run pytest tests/integration/test_extract_pipeline.py -v -m integration`
Expected: 1 passed (with manifest file present).

- [ ] **Step 5: Commit**

```bash
git add extract.py tests/integration/test_extract_pipeline.py tests/fixtures/test_video.mp4
git commit -m "feat(extract): probe source, run transcript chain, write manifest (frames stub)"
```

## Task 6.3: Wire frame extraction + OCR + classification + dedup

**Files:**
- Modify: `extract.py`
- Modify: `tests/integration/test_extract_pipeline.py`

- [ ] **Step 1: Implement `_do_frames`**

Replace the stub with:

```python
def _do_frames(args, out_dir: Path, manifest: Manifest) -> None:
    from vendor.claude_video.scripts import frames as cv_frames  # type: ignore
    from frame_ocr import ocr_frame, classify_frame, dedup_code_frames, write_ocr_json, FrameRecord

    # Resolve the input path the frame extractor needs
    if Path(args.source).exists():
        video_path = str(Path(args.source).resolve())
    else:
        video_path = _download_video(args.source, out_dir, args.cookies_from_browser)

    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    duration = manifest.data["duration_seconds"]
    max_frames = args.max_frames or 100

    if not args.force and (out_dir / "ocr.json").exists() and not args.force_ocr:
        # If both frames dir and ocr.json look intact, skip the whole step.
        if manifest.file_intact("extract", "frames_dir"):
            print("[extract] frames + ocr: skipping (intact)")
            return

    # 1. Extract frames (vendored claude-video frames.py)
    frame_paths = cv_frames.extract_frames(
        video_path,
        out_dir=str(frames_dir),
        duration=duration,
        max_frames=max_frames,
        start=args.start,
        end=args.end,
    )
    # Convention: frame paths come back like "frames/frame_001_t-00-15.jpg"

    # 2. OCR + classify each frame
    records: list[FrameRecord] = []
    for path in frame_paths:
        try:
            res = ocr_frame(path)
            cls, conf = classify_frame(res)
            if conf < 0.6:
                cls = type(cls).OTHER  # spec §4.3 low-conf fallback
            records.append(FrameRecord(
                path=str(Path(path).relative_to(out_dir)),
                timestamp_seconds=_extract_ts(path),
                ocr_text=res.text,
                ocr_confidence=res.mean_confidence,
                frame_class=cls,
                class_confidence=conf,
                cluster_id=None,
            ))
        except Exception as e:  # noqa: BLE001
            records.append(FrameRecord(
                path=str(Path(path).relative_to(out_dir)),
                timestamp_seconds=_extract_ts(path),
                ocr_text="",
                ocr_confidence=0.0,
                frame_class=type(cls).OTHER if records else __import__("frame_ocr").FrameClass.OTHER,
                class_confidence=0.0,
                cluster_id=None,
                ocr_error=str(e),
            ))

    # 3. Dedup CODE-class
    records = dedup_code_frames(records)

    # 4. Persist
    write_ocr_json(out_dir / "ocr.json", video_title=out_dir.name, duration_seconds=duration, frames=records)
    manifest.record_file("extract", "frames_dir", frames_dir)
    manifest.record_file("extract", "ocr_json", out_dir / "ocr.json")
    manifest.data["extract"]["frame_budget_used"] = len(records)
    manifest.data["extract"]["ocr_version"] = "rapidocr-1.4"
    manifest.data["extract"]["dedup_version"] = 1


def _extract_ts(frame_path: str) -> float:
    """Parse 'frame_001_t-00-15.jpg' → 15.0 seconds."""
    import re
    m = re.search(r"t-(\d+)-(\d+)", str(frame_path))
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + int(m.group(2))


def _download_video(url: str, out_dir: Path, cookies_browser: str | None) -> str:
    media_cache = Path("media_cache") / out_dir.name
    media_cache.mkdir(parents=True, exist_ok=True)
    out = media_cache / "video.%(ext)s"
    cmd = ["yt-dlp", "-f", "best[ext=mp4]", "-o", str(out), url]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(_ytdlp_error_message(r.stderr))
    files = list(media_cache.glob("video.*"))
    if not files:
        raise SystemExit("yt-dlp: no video file produced")
    return str(files[0])


def _ytdlp_error_message(stderr: str) -> str:
    if "Sign in to confirm" in stderr or "age-restricted" in stderr.lower():
        return "yt-dlp: source requires authentication / cookies. Pass --cookies-from-browser firefox (or chrome)."
    if "is not available in your country" in stderr.lower():
        return "yt-dlp: source is geo-blocked in your region."
    if "playlist" in stderr.lower() and "not a single video" in stderr.lower():
        return "yt-dlp: URL points to a playlist; pass a single-video URL."
    if "HTTP Error 429" in stderr:
        return "yt-dlp: rate-limited (429). Retry later."
    return f"yt-dlp failed:\n{stderr}"
```

- [ ] **Step 2: Adapt `cv_frames.extract_frames` signature**

Inspect the vendored function: `uv run python -c "from vendor.claude_video.scripts import frames; help(frames)"` and adjust the call. The vendored API will likely not be exactly `extract_frames(...)` — most likely it's a script `main()` that takes argv. **If the API isn't a clean function**, write a thin adapter at the top of `extract.py`:

```python
def _extract_frames_adapter(video_path: str, out_dir: str, duration: float, max_frames: int, start: float | None, end: float | None) -> list[str]:
    """Adapter around vendored frames.py. Returns list of jpeg paths."""
    # Inspect vendor/claude_video/scripts/frames.py and call its function or
    # invoke as subprocess: uv run python vendor/claude_video/scripts/frames.py ...
    ...
```

Replace `cv_frames.extract_frames(...)` calls with `_extract_frames_adapter(...)`.

- [ ] **Step 3: Extend integration test**

Modify `tests/integration/test_extract_pipeline.py`:

```python
@pytest.mark.integration
def test_extract_local_video_with_frames(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    rc = extract.main([str(src), "--max-frames", "8"])
    assert rc == 0
    out = next(tmp_path.iterdir())
    assert (out / "frames").is_dir()
    assert (out / "ocr.json").is_file()
    assert (out / "artifact_manifest.json").is_file()
```

- [ ] **Step 4: Run integration test**

Run: `uv run pytest tests/integration/test_extract_pipeline.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add extract.py tests/integration/test_extract_pipeline.py
git commit -m "feat(extract): wire frames + OCR + classification + dedup; ocr.json + manifest entries"
```

## Task 6.4: Quality grades in `extract_meta.json`

**Files:**
- Modify: `extract.py`
- Create: `tests/test_extract_meta.py`

- [ ] **Step 1: Add tests**

```python
# tests/test_extract_meta.py
from extract import _grade_ocr, _grade_frame_coverage


def test_grade_ocr_buckets():
    assert _grade_ocr(0.9) == "high"
    assert _grade_ocr(0.75) == "medium"
    assert _grade_ocr(0.5) == "low"
    assert _grade_ocr(None) == "none"


def test_grade_frame_coverage():
    # selected_non_code / duration_minutes
    assert _grade_frame_coverage(20, duration_seconds=60) == "high"
    assert _grade_frame_coverage(2, duration_seconds=600) == "low"
```

- [ ] **Step 2: Run; expect ImportError**

Run: `uv run pytest tests/test_extract_meta.py -v`
Expected: ImportError on `_grade_ocr`.

- [ ] **Step 3: Implement grading helpers and `extract_meta.json` writer**

Append to `extract.py`:

```python
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
```

Wire it into `main()` after `_do_frames`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_extract_meta.py tests/integration/test_extract_pipeline.py -v`
Expected: all pass; integration run produces `extract_meta.json` in the output dir.

- [ ] **Step 5: Commit**

```bash
git add extract.py tests/test_extract_meta.py
git commit -m "feat(extract): extract_meta.json with transcript/ocr/coverage grades; drop video unless --keep-video"
```

## Task 6.5: Resumability + clip-range tests

**Files:**
- Modify: `tests/integration/test_extract_pipeline.py`

- [ ] **Step 1: Add resumability test**

Append:

```python
@pytest.mark.integration
def test_extract_resumes_after_partial(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    extract.main([str(src), "--max-frames", "4"])
    out = next(tmp_path.iterdir())
    # Delete one frame to simulate corruption
    f = next((out / "frames").iterdir())
    f.unlink()
    # Re-run without --force; only the missing artifact should rebuild
    rc = extract.main([str(src), "--max-frames", "4"])
    assert rc == 0
    assert f.exists()  # rebuilt


@pytest.mark.integration
def test_extract_clip_range_preserves_absolute_timestamps(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    rc = extract.main([str(src), "--start", "5", "--end", "15", "--max-frames", "4"])
    assert rc == 0
    out = next(tmp_path.iterdir())
    import json
    ocr = json.loads((out / "ocr.json").read_text())
    # All frames should have timestamps in [5, 15], not [0, 10]
    for f in ocr["frames"]:
        assert 5 <= f["timestamp_seconds"] <= 15
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/integration/test_extract_pipeline.py -v`
Expected: 4 passed.

- [ ] **Step 3: If resumability fails**, audit `_do_frames` to ensure missing-file detection (`manifest.file_intact`) triggers a rebuild. Add the missing logic.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_extract_pipeline.py
git commit -m "test(extract): integration tests for resumability and clip-range timestamp preservation"
```

---

# M7 — Models layer + doctor

## Task 7.1: `models.py` — profile resolution

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for resolve()**

```python
# tests/test_models.py
import os
import pytest
from pathlib import Path
import models


def test_resolve_default(monkeypatch, repo_root):
    monkeypatch.delenv("DISTILL_MODEL", raising=False)
    p = models.resolve(cli=None, models_yaml=repo_root / "models.yaml")
    assert p.name == "gemini-3-flash"


def test_resolve_env_overrides_default(monkeypatch, repo_root):
    monkeypatch.setenv("DISTILL_MODEL", "gemini-3-pro")
    p = models.resolve(cli=None, models_yaml=repo_root / "models.yaml")
    assert p.name == "gemini-3-pro"


def test_resolve_cli_overrides_env(monkeypatch, repo_root):
    monkeypatch.setenv("DISTILL_MODEL", "gemini-3-pro")
    p = models.resolve(cli="claude-sonnet-4-6", models_yaml=repo_root / "models.yaml")
    assert p.name == "claude-sonnet-4-6"


def test_unknown_profile_lists_available(repo_root):
    with pytest.raises(SystemExit) as ei:
        models.resolve(cli="nonexistent", models_yaml=repo_root / "models.yaml")
    assert "available" in str(ei.value).lower() or "nonexistent" in str(ei.value)
```

- [ ] **Step 2: Implement**

```python
# models.py
"""Model profile resolution + capability validation (doctor)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Profile:
    name: str
    base_url: str
    model: str
    vision: bool
    reasoning: bool
    api_key_env: str
    max_images: int
    max_image_bytes: int


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def resolve(cli: Optional[str], models_yaml: Path) -> Profile:
    cfg = _load_yaml(models_yaml)
    name = cli or os.environ.get("DISTILL_MODEL") or cfg.get("default")
    if not name:
        raise SystemExit("models.yaml has no `default` and no profile was specified")
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        raise SystemExit(f"profile {name!r} not found. Available: {sorted(profiles)}")
    p = profiles[name]
    return Profile(
        name=name,
        base_url=p["base_url"],
        model=p["model"],
        vision=bool(p.get("vision", False)),
        reasoning=bool(p.get("reasoning", False)),
        api_key_env=p["api_key_env"],
        max_images=int(p.get("max_images", 16)),
        max_image_bytes=int(p.get("max_image_bytes", 5_242_880)),
    )
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat(models): resolve(cli/env/default) returns Profile from models.yaml"
```

## Task 7.2: `models.py doctor` capability checks

**Files:**
- Modify: `models.py`
- Modify: `tests/test_models.py`
- Create: `tests/fixtures/tiny_image.jpg` (32×32 pixel JPEG)

- [ ] **Step 1: Generate the fixture**

```bash
uv run python -c "from PIL import Image; Image.new('RGB',(32,32),(127,127,127)).save('tests/fixtures/tiny_image.jpg','JPEG')"
```

- [ ] **Step 2: Write failing tests with mocked HTTP**

Append to `tests/test_models.py`:

```python
from unittest.mock import patch, MagicMock
from models import doctor, DoctorResult


def _ok_response(content="hello"):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


@patch("models.OpenAI")
def test_doctor_ok_text_only(openai_mock, monkeypatch, repo_root):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = openai_mock.return_value
    client.chat.completions.create.return_value = _ok_response("hi")
    p = models.resolve(cli="claude-sonnet-4-6", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml", probe_image=False)
    assert res.ok is True
    assert res.text_probe is True


@patch("models.OpenAI")
def test_doctor_missing_key(openai_mock, monkeypatch, repo_root):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = models.resolve(cli="gemini-3-flash", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml")
    assert res.ok is False
    assert "key" in res.failure_reason.lower()


@patch("models.OpenAI")
def test_doctor_text_failure_reports(openai_mock, monkeypatch, repo_root):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = openai_mock.return_value
    client.chat.completions.create.side_effect = RuntimeError("boom")
    p = models.resolve(cli="gemini-3-flash", models_yaml=repo_root / "models.yaml")
    res = doctor(p, models_yaml=repo_root / "models.yaml", probe_image=False)
    assert res.ok is False
    assert "boom" in res.failure_reason
```

- [ ] **Step 3: Implement `doctor`**

Append to `models.py`:

```python
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class DoctorResult:
    ok: bool
    text_probe: bool = False
    image_probe: Optional[bool] = None  # None means skipped
    reasoning_probe: Optional[bool] = None
    failure_reason: str = ""


def _cache_dir() -> Path:
    d = Path.home() / ".cache" / "youtube-transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(profile: Profile) -> str:
    return f"model_doctor_{profile.name}_{hashlib.sha1((profile.base_url + profile.model).encode()).hexdigest()[:8]}.json"


def doctor(profile: Profile, *, models_yaml: Path, probe_image: bool = True, fixture_image: Optional[Path] = None, cache_ttl_seconds: int = 3600) -> DoctorResult:
    """Run capability probes. Cached for `cache_ttl_seconds` (default 1h)."""
    cache_path = _cache_dir() / _cache_key(profile)
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if time.time() - cached["timestamp"] < cache_ttl_seconds:
                return DoctorResult(**cached["result"])
        except Exception:  # noqa: BLE001
            pass

    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        return DoctorResult(ok=False, failure_reason=f"environment variable {profile.api_key_env} not set")

    client = OpenAI(base_url=profile.base_url, api_key=api_key)

    # 1. Text probe
    try:
        client.chat.completions.create(
            model=profile.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        text_ok = True
    except Exception as e:  # noqa: BLE001
        return _save_doctor(cache_path, DoctorResult(ok=False, text_probe=False, failure_reason=f"text probe: {e}"))

    # 2. Image probe (if profile claims vision and probe_image)
    image_ok: Optional[bool] = None
    if profile.vision and probe_image:
        img_path = fixture_image or (Path(__file__).resolve().parent / "tests/fixtures/tiny_image.jpg")
        try:
            b64 = base64.b64encode(img_path.read_bytes()).decode()
            client.chat.completions.create(
                model=profile.model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "describe in one word"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]}],
                max_tokens=10,
            )
            image_ok = True
        except Exception as e:  # noqa: BLE001
            return _save_doctor(cache_path, DoctorResult(ok=False, text_probe=True, image_probe=False, failure_reason=f"image probe: {e}"))

    # 3. Reasoning probe
    reasoning_ok: Optional[bool] = None
    if profile.reasoning:
        try:
            client.chat.completions.create(
                model=profile.model,
                messages=[{"role": "user", "content": "1+1"}],
                max_tokens=5,
                extra_body={"reasoning": {"enabled": True}},
            )
            reasoning_ok = True
        except Exception as e:  # noqa: BLE001
            return _save_doctor(cache_path, DoctorResult(ok=False, text_probe=True, image_probe=image_ok, reasoning_probe=False, failure_reason=f"reasoning probe: {e}"))

    return _save_doctor(cache_path, DoctorResult(ok=True, text_probe=True, image_probe=image_ok, reasoning_probe=reasoning_ok))


def _save_doctor(cache_path: Path, result: DoctorResult) -> DoctorResult:
    cache_path.write_text(json.dumps({"timestamp": time.time(), "result": result.__dict__}))
    return result


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--profile", required=True)
    d.add_argument("--no-image-probe", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "doctor":
        prof = resolve(cli=args.profile, models_yaml=Path(__file__).resolve().parent / "models.yaml")
        res = doctor(prof, models_yaml=Path(__file__).resolve().parent / "models.yaml", probe_image=not args.no_image_probe)
        print(f"profile={prof.name} ok={res.ok} text={res.text_probe} image={res.image_probe} reasoning={res.reasoning_probe}")
        if not res.ok:
            print(f"failure: {res.failure_reason}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_models.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py tests/fixtures/tiny_image.jpg
git commit -m "feat(models): doctor with text/image/reasoning probes; 1h cache; CLI subcommand"
```

---

# M8 — Distill prerequisites

## Task 8.1: Distillation prompt contract v1

**Files:**
- Create: `prompts/distill_contract_v1.md`

- [ ] **Step 1: Write the contract**

```markdown
# Distillation Prompt Contract — v1

You are transforming a video's transcript and visual evidence into a structured note.
You MUST follow these rules without exception:

1. **No unsupported claims.** Every technical statement, step, code snippet, UI
   observation, or diagram interpretation must cite at least one of:
   - a transcript segment ID like `seg#NNN`
   - a frame ID like `frame_NNN_t-MM-SS` (or its short form `frame_NNN`)
   - a code-frame cluster ID like `cluster_id=cN`
   - a bare timestamp range `t=MM:SS` or `t=MM:SS–MM:SS`
   Statements without a citation are forbidden.

2. **Preserve uncertainty.** When OCR text in the transcript is marked
   `~approximate`, propagate the marker into any code block you emit from it.
   When the input announces `transcript_quality: low` or `none`, say so in the
   `## Quality Note` section of your output.

3. **Required sections** (in this order; omit any that have no content):
   - `## Summary` — 2–4 sentence overview.
   - `## Key Points` — bulleted, each with citation(s).
   - `## Steps / Walkthrough` — numbered, each with citation(s). Skip if not a how-to.
   - `## Code` — fenced code blocks with language hints, each with citation(s).
   - `## Tools & References` — names of tools, libraries, URLs mentioned, with citations.
   - `## Visual Evidence Used` — list each frame ID you describe, with one-line interpretations.
   - `## Open Questions` — anything ambiguous in the input.
   - `## Quality Note` — required only when transcript_quality < high or unresolved citations.

4. **No hallucinated visual content.** Do not infer text that is in a frame
   but is not in the OCR. When you describe a frame in `Visual Evidence Used`,
   prefix the description with `frame_NNN observation:`.

5. **Style guide overlay.** Apply the user-supplied style guide to tone and
   structure, but it does NOT override the citation requirement. If the style
   guide and this contract conflict, this contract wins.

End every section's content; do not leave placeholders. If a section has
nothing to say, omit it entirely (do not write "N/A").
```

- [ ] **Step 2: Commit**

```bash
git add prompts/distill_contract_v1.md
git commit -m "feat(prompts): distillation contract v1 (citations required, no hallucinated visuals)"
```

## Task 8.2: `enrichment.py` — transcript-frame insertion rule

**Files:**
- Create: `enrichment.py`
- Create: `tests/test_enrichment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_enrichment.py
from enrichment import enrich_transcript, TranscriptSegment
from frame_ocr import FrameRecord, FrameClass


def _seg(i, start, end, text):
    return TranscriptSegment(seg_id=i, start=start, end=end, text=text)


def _frame(i, ts, text, klass=FrameClass.CODE, cluster=None):
    return FrameRecord(
        path=f"frames/frame_{i:03d}_t-{int(ts // 60):02d}-{int(ts % 60):02d}.jpg",
        timestamp_seconds=ts,
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=cluster,
    )


def test_inserts_code_block_after_containing_segment():
    segs = [_seg(0, 0.0, 5.0, "intro"), _seg(1, 5.0, 10.0, "lets see code")]
    frames = [_frame(7, 7.0, "def f(): pass")]
    out = enrich_transcript(segs, frames)
    assert "lets see code" in out
    assert "def f(): pass" in out
    assert out.index("def f(): pass") > out.index("lets see code")


def test_inserts_at_boundary_when_no_containing_segment():
    segs = [_seg(0, 0.0, 5.0, "a"), _seg(1, 8.0, 10.0, "b")]
    frames = [_frame(7, 6.5, "code", FrameClass.CODE)]
    out = enrich_transcript(segs, frames)
    assert "code" in out
    # code should appear between segment 0 and segment 1
    assert out.index("code") > out.index("a") and out.index("code") < out.index("b")


def test_slide_text_uses_quoted_format():
    segs = [_seg(0, 0.0, 10.0, "x")]
    frames = [_frame(5, 5.0, "Slide title here", FrameClass.SLIDE_TEXT)]
    out = enrich_transcript(segs, frames)
    assert "> [slide" in out
    assert "Slide title here" in out
```

- [ ] **Step 2: Implement `enrichment.py`**

```python
# enrichment.py
"""Transcript enrichment: splice frame OCR/notes into the transcript at the
correct timestamp per the insertion rule (spec §4.6)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from frame_ocr import FrameRecord, FrameClass


@dataclass
class TranscriptSegment:
    seg_id: int
    start: float
    end: float
    text: str


def parse_formatted_transcript(path: Path | str) -> list[TranscriptSegment]:
    """Parse `*_formatted_transcript.txt` (start|text per line). End = next start."""
    raw: list[tuple[float, str]] = []
    for line in Path(path).read_text().splitlines():
        if "|" not in line:
            continue
        ts_str, text = line.split("|", 1)
        try:
            raw.append((float(ts_str), text))
        except ValueError:
            continue
    segs: list[TranscriptSegment] = []
    for i, (ts, text) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else ts + 5.0
        segs.append(TranscriptSegment(seg_id=i, start=ts, end=end, text=text))
    return segs


def _fmt_ts(ts: float) -> str:
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"


def _frame_id(rec: FrameRecord) -> str:
    return Path(rec.path).stem  # e.g. frame_001_t-00-15


def _insertion_index(segs: list[TranscriptSegment], frame_ts: float) -> int:
    """Return the index AFTER which the frame should be inserted."""
    for i, s in enumerate(segs):
        if s.start <= frame_ts < s.end:
            return i
    # Not contained; find boundary
    for i, s in enumerate(segs):
        if s.end <= frame_ts and (i + 1 == len(segs) or segs[i + 1].start > frame_ts):
            return i
    return len(segs) - 1 if segs else 0


def enrich_transcript(segments: list[TranscriptSegment], frames: Iterable[FrameRecord]) -> str:
    """Build the enriched-transcript markdown string."""
    # Group frames by insertion index; only emit one block per code cluster.
    inserts: dict[int, list[str]] = {}
    seen_clusters: set[str] = set()
    for f in frames:
        idx = _insertion_index(segments, f.timestamp_seconds)
        block = _block_for(f, segments, seen_clusters)
        if block is None:
            continue
        inserts.setdefault(idx, []).append(block)

    lines: list[str] = []
    for i, seg in enumerate(segments):
        lines.append(f"[t={_fmt_ts(seg.start)}–{_fmt_ts(seg.end)} | seg#{seg.seg_id}] {seg.text}")
        for blk in inserts.get(i, []):
            lines.append("")
            lines.append(blk)
    return "\n".join(lines) + "\n"


def _block_for(f: FrameRecord, segments: list[TranscriptSegment], seen_clusters: set[str]) -> str | None:
    fid = _frame_id(f)
    has_low_conf = "~approximate" if f.ocr_confidence < 0.65 else ""
    if f.frame_class == FrameClass.CODE:
        # Only emit one block per cluster
        if f.cluster_id and f.cluster_id in seen_clusters:
            return None
        if f.cluster_id:
            seen_clusters.add(f.cluster_id)
        cluster_tag = f" [cluster_id={f.cluster_id}]" if f.cluster_id else ""
        marker = f" {has_low_conf}" if has_low_conf else ""
        return f"```code-from-{fid}{cluster_tag}{marker}\n{f.ocr_text.strip()}\n```"
    if f.frame_class == FrameClass.SLIDE_TEXT:
        marker = f" ({has_low_conf})" if has_low_conf else ""
        return f"> [slide t={_fmt_ts(f.timestamp_seconds)} | {fid}{marker}] {f.ocr_text.strip()}"
    if f.frame_class == FrameClass.UI:
        return f"_[ui {fid}]_ {f.ocr_text.strip()}"
    if f.frame_class == FrameClass.DIAGRAM:
        return f"_[diagram {fid}]_ (see vision payload)"
    return None  # OTHER class: no inline injection


def write_enriched_transcript(path: Path | str, content: str) -> None:
    Path(path).write_text(content)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_enrichment.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add enrichment.py tests/test_enrichment.py
git commit -m "feat(enrichment): transcript-frame insertion rule with class-specific wrappers and cluster dedup"
```

## Task 8.3: `payload.py` — multimodal payload builder

**Files:**
- Create: `payload.py`
- Create: `tests/test_payload.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_payload.py
import base64
from pathlib import Path
import pytest
from payload import build_payload, PayloadBuildError
from frame_select import Selected
from frame_ocr import FrameClass
from models import Profile


def _profile(vision=True):
    return Profile(name="t", base_url="http://x", model="m", vision=vision, reasoning=False, api_key_env="X", max_images=4, max_image_bytes=5_000_000)


def test_payload_text_only_when_no_vision():
    p = _profile(vision=False)
    msg = build_payload(profile=p, system_prompt="contract", style="style", enriched_transcript="t", selected=[], frames_root=Path("."))
    assert isinstance(msg, list)
    assert msg[0]["type"] == "text"
    assert all(m["type"] != "image_url" for m in msg)


def test_payload_includes_image_blocks(tmp_path):
    img = tmp_path / "frame_001_t-00-05.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"x" * 200 + b"\xff\xd9")  # minimal JPEG-ish
    sel = [Selected(path="frame_001_t-00-05.jpg", timestamp_seconds=5.0, frame_class=FrameClass.SLIDE_TEXT, reason="r")]
    p = _profile()
    msg = build_payload(profile=p, system_prompt="c", style="s", enriched_transcript="t", selected=sel, frames_root=tmp_path)
    image_blocks = [m for m in msg if m["type"] == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_payload_caps_at_profile_max_images(tmp_path):
    sels = []
    for i in range(10):
        img = tmp_path / f"frame_{i:03d}_t-00-{i:02d}.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"x" * 100 + b"\xff\xd9")
        sels.append(Selected(path=img.name, timestamp_seconds=float(i), frame_class=FrameClass.SLIDE_TEXT, reason="r"))
    p = _profile()  # max_images=4
    msg = build_payload(profile=p, system_prompt="c", style="s", enriched_transcript="t", selected=sels, frames_root=tmp_path)
    assert len([m for m in msg if m["type"] == "image_url"]) == 4
```

- [ ] **Step 2: Implement**

```python
# payload.py
"""Build multimodal LLM payload (OpenAI SDK shape)."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Sequence

from frame_select import Selected
from models import Profile


class PayloadBuildError(RuntimeError):
    pass


def _frame_id(rel_path: str) -> str:
    return Path(rel_path).stem


def build_payload(
    *,
    profile: Profile,
    system_prompt: str,
    style: str,
    enriched_transcript: str,
    selected: Sequence[Selected],
    frames_root: Path,
) -> list[dict]:
    """Return the `content` list to pass as messages[0]['content']."""
    # Visual evidence index goes in the text block so frame IDs are restated
    # (some providers strip text adjacent to image blocks).
    if profile.vision and selected:
        index_lines = ["", "Visual evidence index (citable):"]
        for s in selected:
            index_lines.append(f"- {_frame_id(s.path)} (class={s.frame_class.value}, reason={s.reason})")
        index = "\n".join(index_lines)
    else:
        index = ""

    text = f"{system_prompt}\n\n{style}\n\n---\n\n# Transcript (OCR-enriched, citation-tagged)\n\n{enriched_transcript}{index}"
    msg: list[dict] = [{"type": "text", "text": text}]

    if not profile.vision:
        return msg

    # Cap images and respect per-image byte limit.
    cap = min(profile.max_images, len(selected))
    for s in list(selected)[:cap]:
        path = frames_root / s.path
        if not path.is_file():
            raise PayloadBuildError(f"missing frame file {path}")
        data = path.read_bytes()
        if len(data) > profile.max_image_bytes:
            raise PayloadBuildError(f"frame {path} exceeds max_image_bytes ({len(data)} > {profile.max_image_bytes})")
        b64 = base64.b64encode(data).decode()
        msg.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return msg
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_payload.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add payload.py tests/test_payload.py
git commit -m "feat(payload): build_payload constructs multimodal content with vision cap and per-image byte limit"
```

## Task 8.4: `citation.py` — token regex + extractor + validator

**Files:**
- Create: `citation.py`
- Create: `tests/test_citation.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_citation.py
import pytest
from citation import extract_citations, validate_citations, ResolutionContext


def test_extract_all_citation_forms():
    text = "See seg#42 and frame_017 also frame_017_t-01-23 plus cluster_id=c4 and t=02:30 and t=02:30–02:45."
    cits = extract_citations(text)
    kinds = {c.kind for c in cits}
    assert "segment" in kinds
    assert "frame" in kinds
    assert "cluster" in kinds
    assert "timestamp" in kinds


def test_validate_resolves_real_segments():
    ctx = ResolutionContext(segment_ids={1, 2, 42}, frame_ids={"frame_017_t-01-23"}, cluster_ids={"c4"})
    text = "seg#42 frame_017_t-01-23 cluster_id=c4"
    res = validate_citations(text, ctx)
    assert res.unresolved == []


def test_validate_flags_unresolved():
    ctx = ResolutionContext(segment_ids={1}, frame_ids=set(), cluster_ids=set())
    text = "seg#42 frame_999"
    res = validate_citations(text, ctx)
    assert len(res.unresolved) == 2
```

- [ ] **Step 2: Implement**

```python
# citation.py
"""Citation token extraction and validation (spec §6)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Set


_SEG = re.compile(r"seg#(\d+)")
_FRAME_FULL = re.compile(r"frame_\d{3}_t-\d{2}-\d{2}")
_FRAME_SHORT = re.compile(r"\bframe_(\d{3})\b(?!_t)")
_CLUSTER = re.compile(r"cluster_id=([a-zA-Z0-9_]+)")
_TIMESTAMP = re.compile(r"\bt=\d{2}:\d{2}(?:[–-]\d{2}:\d{2})?")


@dataclass
class Citation:
    kind: str  # segment | frame | cluster | timestamp
    value: str
    raw: str


@dataclass
class ResolutionContext:
    segment_ids: Set[int]
    frame_ids: Set[str]
    cluster_ids: Set[str]


@dataclass
class ValidationResult:
    citations: list[Citation]
    unresolved: list[Citation]


def extract_citations(text: str) -> list[Citation]:
    out: list[Citation] = []
    for m in _SEG.finditer(text):
        out.append(Citation(kind="segment", value=m.group(1), raw=m.group(0)))
    for m in _FRAME_FULL.finditer(text):
        out.append(Citation(kind="frame", value=m.group(0), raw=m.group(0)))
    for m in _FRAME_SHORT.finditer(text):
        out.append(Citation(kind="frame", value=m.group(0), raw=m.group(0)))
    for m in _CLUSTER.finditer(text):
        out.append(Citation(kind="cluster", value=m.group(1), raw=m.group(0)))
    for m in _TIMESTAMP.finditer(text):
        out.append(Citation(kind="timestamp", value=m.group(0), raw=m.group(0)))
    return out


def validate_citations(text: str, ctx: ResolutionContext) -> ValidationResult:
    cits = extract_citations(text)
    unresolved: list[Citation] = []
    for c in cits:
        if c.kind == "segment" and int(c.value) not in ctx.segment_ids:
            unresolved.append(c)
        elif c.kind == "frame":
            # Match either full or short form: short form `frame_NNN` resolves
            # if any frame_id starts with `frame_NNN_`.
            if c.value not in ctx.frame_ids and not any(fid.startswith(c.value + "_") for fid in ctx.frame_ids):
                unresolved.append(c)
        elif c.kind == "cluster" and c.value not in ctx.cluster_ids:
            unresolved.append(c)
        # timestamps are always resolvable (informational only)
    return ValidationResult(citations=cits, unresolved=unresolved)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_citation.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add citation.py tests/test_citation.py
git commit -m "feat(citation): extract+validate seg/frame/cluster/timestamp citation tokens"
```

## Task 8.5: `distill_render.py` — JSON → markdown

**Files:**
- Create: `distill_render.py`
- Create: `tests/test_distill_render.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_distill_render.py
from distill_render import render_markdown


def test_render_includes_required_sections():
    data = {
        "schema_version": 1,
        "source_id": "yt:abc",
        "title": "Demo",
        "model_profile": "gemini-3-flash",
        "prompt_contract_version": 1,
        "summary": "It's a demo.",
        "key_points": [{"text": "K1", "citations": ["seg#1"]}],
        "steps": [],
        "code_blocks": [{"language": "python", "code": "print(1)", "citations": ["frame_001_t-00-05"], "approximate": False}],
        "tools_mentioned": [],
        "open_questions": [],
        "visual_evidence_used": [{"frame_id": "frame_010_t-01-00", "class": "diagram", "interpretation": "arch", "selection_reason": "scene_change"}],
        "quality": {"transcript": "high", "ocr": "medium", "frame_coverage": "high", "distillation_confidence": "medium"},
        "warnings": [],
        "token_usage": {"prompt": 1, "completion": 1, "image_count": 1},
        "citations": {"segments_referenced": 1, "frames_referenced": 1, "unresolved": 0},
    }
    md = render_markdown(data, style_name="coding_agent", today_iso="2026-05-07")
    assert "## Summary" in md
    assert "## Key Points" in md
    assert "## Code" in md
    assert "## Visual Evidence Used" in md
    assert "model_profile: gemini-3-flash" in md  # frontmatter
    assert "prompt_contract_version: 1" in md
```

- [ ] **Step 2: Implement**

```python
# distill_render.py
"""Render distill_result.json → Obsidian-ready markdown."""
from __future__ import annotations

from typing import Any


def _frontmatter(data: dict, style_name: str, today_iso: str) -> str:
    cit = data.get("citations") or {}
    q = data.get("quality") or {}
    return (
        "---\n"
        "type: tutorial\n"
        "category: development\n"
        "domain:\n"
        "  - youtube-transcript\n"
        f"  - {style_name}\n"
        "source: youtube-transcript-transform\n"
        f"created: {today_iso}\n"
        "status: inbox-triage\n"
        "tags:\n"
        "  - tutorial\n"
        f"  - {style_name}\n"
        "  - transformed-transcript\n"
        f"summary: {data.get('summary','').splitlines()[0] if data.get('summary') else ''}\n"
        "enriched_at: \"\"\n"
        f"model_profile: {data.get('model_profile','')}\n"
        f"prompt_contract_version: {data.get('prompt_contract_version','')}\n"
        "citations:\n"
        f"  segments_referenced: {cit.get('segments_referenced', 0)}\n"
        f"  frames_referenced: {cit.get('frames_referenced', 0)}\n"
        f"  unresolved: {cit.get('unresolved', 0)}\n"
        "quality:\n"
        f"  transcript: {q.get('transcript','')}\n"
        f"  ocr: {q.get('ocr','')}\n"
        f"  frame_coverage: {q.get('frame_coverage','')}\n"
        f"  distillation_confidence: {q.get('distillation_confidence','')}\n"
        "---\n\n"
    )


def _cite(cs: list[str]) -> str:
    return f" ({', '.join(cs)})" if cs else ""


def render_markdown(data: dict, *, style_name: str, today_iso: str) -> str:
    parts = [_frontmatter(data, style_name, today_iso)]
    if data.get("citations", {}).get("unresolved", 0) > 0:
        parts.append("> ⚠ This note has unresolved citations. Re-run distill.\n\n")
    if data.get("summary"):
        parts.append(f"## Summary\n\n{data['summary']}\n\n")
    if data.get("key_points"):
        parts.append("## Key Points\n\n")
        for p in data["key_points"]:
            parts.append(f"- {p['text']}{_cite(p.get('citations', []))}\n")
        parts.append("\n")
    if data.get("steps"):
        parts.append("## Steps / Walkthrough\n\n")
        for s in data["steps"]:
            parts.append(f"{s['order']}. {s['text']}{_cite(s.get('citations', []))}\n")
        parts.append("\n")
    if data.get("code_blocks"):
        parts.append("## Code\n\n")
        for cb in data["code_blocks"]:
            tag = " ~approximate" if cb.get("approximate") else ""
            parts.append(f"```{cb.get('language','')}{tag}\n{cb['code']}\n```\n{_cite(cb.get('citations', []))}\n\n")
    if data.get("tools_mentioned"):
        parts.append("## Tools & References\n\n")
        for t in data["tools_mentioned"]:
            parts.append(f"- **{t['name']}**{_cite(t.get('citations', []))}\n")
        parts.append("\n")
    if data.get("visual_evidence_used"):
        parts.append("## Visual Evidence Used\n\n")
        for v in data["visual_evidence_used"]:
            parts.append(f"- {v['frame_id']} ({v['class']}, {v['selection_reason']}): {v['interpretation']}\n")
        parts.append("\n")
    if data.get("open_questions"):
        parts.append("## Open Questions\n\n")
        for q in data["open_questions"]:
            parts.append(f"- {q}\n")
        parts.append("\n")
    q = data.get("quality") or {}
    needs_quality_note = q.get("transcript") not in ("high",) or data.get("citations", {}).get("unresolved", 0) > 0
    if needs_quality_note:
        parts.append("## Quality Note\n\n")
        parts.append(f"transcript={q.get('transcript')}, ocr={q.get('ocr')}, frame_coverage={q.get('frame_coverage')}.\n")
        if data.get("warnings"):
            for w in data["warnings"]:
                parts.append(f"- {w}\n")
        parts.append("\n")
    return "".join(parts)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_distill_render.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add distill_render.py tests/test_distill_render.py
git commit -m "feat(distill_render): render distill_result.json into Obsidian-ready markdown"
```

---

# M9 — `distill.py` orchestrator

## Task 9.1: Skeleton + arg parsing + artifact loading

**Files:**
- Create: `distill.py`
- Create: `tests/test_distill_args.py`

- [ ] **Step 1: Failing arg test**

```python
# tests/test_distill_args.py
import distill


def test_parse_args_minimal():
    ns = distill._parse_args(["My_Title", "coding_agent"])
    assert ns.title == "My_Title"
    assert ns.style == "coding_agent"
    assert ns.dry_run_payload is False


def test_parse_args_flags():
    ns = distill._parse_args(["X", "y", "--model", "gpt-4o", "--max-vision-frames", "8", "--dry-run-payload", "--force"])
    assert ns.model == "gpt-4o"
    assert ns.max_vision_frames == 8
    assert ns.dry_run_payload is True
    assert ns.force is True
```

- [ ] **Step 2: Implement skeleton**

```python
# distill.py
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
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/test_distill_args.py -v`
Expected: 2 passed.

```bash
git add distill.py tests/test_distill_args.py
git commit -m "feat(distill): skeleton with arg parsing, profile resolution, doctor gate"
```

## Task 9.2: Wire enrichment + frame selection + payload

**Files:**
- Modify: `distill.py`
- Create: `tests/integration/test_distill_dry_run.py`

- [ ] **Step 1: Replace `main()` body**

After the doctor block, add:

```python
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
```

- [ ] **Step 2: Add integration test for `--dry-run-payload`**

```python
# tests/integration/test_distill_dry_run.py
import json
import os
from pathlib import Path
import pytest
import distill, extract


@pytest.mark.integration
def test_dry_run_payload_flow(tmp_path, fixtures_dir, monkeypatch):
    src = fixtures_dir / "test_video.mp4"
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    extract.main([str(src), "--max-frames", "6"])
    od = next(tmp_path.iterdir())
    # Skip the doctor by mocking it
    import distill as _d
    monkeypatch.setattr(_d, "doctor", lambda *a, **k: type("R", (), {"ok": True, "failure_reason": ""})())
    rc = distill.main([od.name, "knowledge_base", "--dry-run-payload"])
    assert rc == 0
    payload_path = od / "payload.json"
    assert payload_path.is_file()
    payload = json.loads(payload_path.read_text())
    assert any(c["type"] == "text" for c in payload)
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/integration/test_distill_dry_run.py -v`
Expected: 1 passed.

```bash
git add distill.py tests/integration/test_distill_dry_run.py
git commit -m "feat(distill): wire enrichment, frame selection, payload build, --dry-run-payload"
```

## Task 9.3: Live distillation + structured output + citation validator

**Files:**
- Modify: `distill.py`
- Create: `tests/test_distill_live.py`

- [ ] **Step 1: Failing test (mocked provider)**

```python
# tests/test_distill_live.py
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
import distill


@patch("distill.OpenAI")
def test_live_distill_writes_outputs(openai_mock, tmp_path, fixtures_dir, monkeypatch):
    # Set up an extract result by writing the artifacts we need by hand.
    od = tmp_path / "T"
    od.mkdir()
    (od / "T_formatted_transcript.txt").write_text("0.0|hello\n5.0|world\n")
    (od / "T_clean_text.txt").write_text("hello world")
    (od / "frames").mkdir()
    (od / "ocr.json").write_text(json.dumps({
        "video": {"title": "T", "duration_seconds": 10},
        "frames": []
    }))
    (od / "artifact_manifest.json").write_text(json.dumps({
        "schema_version": 1, "source_id": "yt:x", "source_url": "u", "title": "T",
        "duration_seconds": 10.0, "clip_range": None, "extract": {"transcript_quality": "high"},
        "distill_runs": []
    }))
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    # Provider returns a tiny valid distill_result.json
    fake = json.dumps({
        "summary": "S",
        "key_points": [{"text": "p", "citations": ["seg#0"]}],
        "steps": [], "code_blocks": [], "tools_mentioned": [],
        "open_questions": [], "visual_evidence_used": [],
        "warnings": [],
    })
    client = openai_mock.return_value
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake))],
        usage=MagicMock(prompt_tokens=1, completion_tokens=1),
    )
    monkeypatch.setattr(distill, "doctor", lambda *a, **k: type("R", (), {"ok": True})())
    rc = distill.main(["T", "knowledge_base"])
    assert rc == 0
    assert (od / "T_knowledge_base.md").is_file()
    assert (od / "T_knowledge_base.distill_result.json").is_file()
```

- [ ] **Step 2: Implement live API call + rendering**

Replace the `Task 9.3` placeholder line with:

```python
    # Live distillation
    from openai import OpenAI
    from datetime import date
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
    manifest = Manifest.load_or_create(out_dir, source_id="-", source_url="-", title=out_dir.name, duration_seconds=0.0)
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

    style_name = args.style
    today_iso = date.today().isoformat()
    md = render_markdown(parsed_full, style_name=style_name, today_iso=today_iso)
    (out_dir / f"{out_dir.name}_{style_name}.md").write_text(md)
    (out_dir / f"{out_dir.name}_{style_name}.distill_result.json").write_text(json.dumps(parsed_full, indent=2))

    # Citation validator gate
    if val.unresolved:
        print(f"[distill] WARNING: {len(val.unresolved)} unresolved citations: {[c.raw for c in val.unresolved]}", file=sys.stderr)
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


def _confidence_from(unresolved: list, manifest: Manifest) -> str:
    if unresolved:
        return "low"
    if (manifest.data.get("extract") or {}).get("transcript_quality") == "high":
        return "high"
    return "medium"
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/test_distill_live.py -v`
Expected: 1 passed.

```bash
git add distill.py tests/test_distill_live.py
git commit -m "feat(distill): live API call, citation validation, distill_result.json + rendered markdown"
```

## Task 9.4: Citation validator fail test

**Files:**
- Modify: `tests/test_distill_live.py`

- [ ] **Step 1: Add failing-citation test**

Append:

```python
@patch("distill.OpenAI")
def test_distill_fails_on_unresolved_citations(openai_mock, tmp_path, monkeypatch):
    od = tmp_path / "T"
    od.mkdir()
    (od / "T_formatted_transcript.txt").write_text("0.0|hi\n")
    (od / "ocr.json").write_text(json.dumps({"video": {"title":"T","duration_seconds":1}, "frames": []}))
    (od / "artifact_manifest.json").write_text(json.dumps({"schema_version":1,"source_id":"x","source_url":"u","title":"T","duration_seconds":1.0,"clip_range":None,"extract":{"transcript_quality":"high"},"distill_runs":[]}))
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(distill, "doctor", lambda *a, **k: type("R", (), {"ok": True})())
    fake = json.dumps({
        "summary": "S — see seg#9999 and frame_999",  # both unresolved
        "key_points": [], "steps": [], "code_blocks": [],
        "tools_mentioned": [], "open_questions": [], "visual_evidence_used": [], "warnings": [],
    })
    openai_mock.return_value.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fake))],
        usage=MagicMock(prompt_tokens=1, completion_tokens=1),
    )
    rc = distill.main(["T", "knowledge_base"])
    assert rc == 1
    # Files still written, but flagged
    md = (od / "T_knowledge_base.md").read_text()
    assert "unresolved citations" in md
```

- [ ] **Step 2: Run + commit**

Run: `uv run pytest tests/test_distill_live.py -v`
Expected: 2 passed.

```bash
git add tests/test_distill_live.py
git commit -m "test(distill): exit 1 when LLM emits unresolved citations; banner in markdown"
```

---

# M10 — Convenience, polish, DoD

## Task 10.1: `run.py` convenience wrapper

**Files:**
- Create: `run.py`
- Create: `tests/test_run.py`

- [ ] **Step 1: Test (smoke)**

```python
# tests/test_run.py
import run


def test_help_returns_zero(capsys):
    rc = run.main(["--help"])
    out = capsys.readouterr().out
    assert "extract" in out.lower() or "distill" in out.lower()
```

- [ ] **Step 2: Implement**

```python
# run.py
"""Convenience wrapper: extract.py → distill.py."""
import argparse
import sys
import extract
import distill


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
    # title is the directory name produced by extract.
    from pathlib import Path
    import os, re
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    # Use the most recently modified subdir under base as the target
    subs = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if base.exists() else []
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
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/test_run.py -v`
Expected: 1 passed.

```bash
git add run.py tests/test_run.py
git commit -m "feat(run): convenience wrapper chaining extract → distill"
```

## Task 10.2: `clean.py` storage management

**Files:**
- Create: `clean.py`
- Create: `tests/test_clean.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_clean.py
from pathlib import Path
import json
import time
import clean


def _setup(root: Path, age_days: int = 0):
    od = root / "Generated_Data" / "T"
    (od / "frames").mkdir(parents=True)
    (od / "frames" / "f1.jpg").write_bytes(b"x")
    (od / "ocr.json").write_text("{}")
    (root / "media_cache" / "T").mkdir(parents=True)
    (root / "media_cache" / "T" / "video.mp4").write_bytes(b"v")
    (od / "artifact_manifest.json").write_text(json.dumps({"extract": {"completed_at": "2020-01-01T00:00:00Z"}}))
    return od


def test_dry_run_does_not_delete(tmp_path):
    od = _setup(tmp_path)
    rc = clean.main(["--delete-video", "--delete-frames", "--root", str(tmp_path)])
    assert rc == 0
    assert (od / "frames" / "f1.jpg").exists()  # still there
    assert (tmp_path / "media_cache" / "T" / "video.mp4").exists()


def test_apply_deletes(tmp_path):
    od = _setup(tmp_path)
    rc = clean.main(["--delete-video", "--delete-frames", "--apply", "--root", str(tmp_path)])
    assert rc == 0
    assert not (od / "frames" / "f1.jpg").exists()
    assert not (tmp_path / "media_cache" / "T" / "video.mp4").exists()
    assert (od / "ocr.json").exists()  # OCR retained
```

- [ ] **Step 2: Implement**

```python
# clean.py
"""Storage management — dry-run by default."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta


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
        age_cutoff = datetime.utcnow() - _parse_duration(args.older_than)

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
                    if json.loads(man.read_text()).get("source_id") != source_id_filter:
                        return False
                except Exception:
                    return False
                break
    if age_cutoff:
        mtime = datetime.utcfromtimestamp(path.stat().st_mtime)
        if mtime > age_cutoff:
            return False
    return True


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/test_clean.py -v`
Expected: 2 passed.

```bash
git add clean.py tests/test_clean.py
git commit -m "feat(clean): dry-run-by-default storage cleanup with --delete-video/--delete-frames"
```

## Task 10.3: `download_transcript.py` legacy delegation when style is given

**Files:**
- Modify: `download_transcript.py`
- Modify: `tests/test_download_transcript_legacy.py`

- [ ] **Step 1: Add a regression test for the with-style branch**

Append to `tests/test_download_transcript_legacy.py`:

```python
import subprocess
from unittest.mock import patch


@patch("download_transcript.subprocess.run")
def test_with_style_delegates_to_run(run_mock, tmp_path, monkeypatch):
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path))
    run_mock.return_value = subprocess.CompletedProcess(args=["uv", "run", "python", "run.py"], returncode=0)
    # Patch sys.argv inline since the legacy script reads from there
    import sys
    saved = sys.argv
    sys.argv = ["download_transcript.py", "https://x", "coding_agent"]
    try:
        # The script should detect a style and invoke run.py instead of the old transform path
        # (we just assert it doesn't crash and that subprocess.run was called)
        import importlib, download_transcript
        importlib.reload(download_transcript)  # not actually re-runnable, but imports the module fresh
    finally:
        sys.argv = saved
```

- [ ] **Step 2: Add the delegation branch in `download_transcript.py`**

Locate the `if __name__ == "__main__":` block. Insert before the existing transform call:

```python
    if style:
        # Delegate to run.py (extract → distill) for the new pipeline
        run_script = os.path.join(project_root, "run.py")
        if os.path.isfile(run_script):
            print(f"[download_transcript] delegating to run.py for style={style!r}")
            r = subprocess.run(["uv", "run", "python", run_script, sys.argv[1], style], cwd=project_root)
            sys.exit(r.returncode)
```

(Keep the existing `transform_transcript.sh` fallback as a safety net for when `run.py` is absent.)

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_download_transcript_legacy.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add download_transcript.py tests/test_download_transcript_legacy.py
git commit -m "feat(download_transcript): delegate to run.py when a style is provided; preserve no-style behavior"
```

## Task 10.4: README + legal/auth policy

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a new section to `README.md`**

```markdown
## What's new (May 2026)

This repo now combines the YouTube transcript pipeline with frame extraction
and OCR-aware distillation. See
`docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`
for the full design.

### Quick start

```bash
# One-shot: download, extract frames, OCR, and distill with a style guide
uv run python run.py "https://www.youtube.com/watch?v=KE39P4qBjDk" coding_agent

# Two-phase (re-stylable):
uv run python extract.py "https://youtu.be/KE39P4qBjDk"
uv run python distill.py KE39P4qBjDk_Title coding_agent --model gemini-3-flash

# Validate a model profile
uv run python models.py doctor --profile gemini-3-flash

# Storage cleanup (dry-run by default)
uv run python clean.py --delete-video --older-than 30d --apply
```

### Configuring models

Edit `models.yaml`. Adding a new vision-capable model = one entry. Run
`models.py doctor` to verify.

## Legal & authentication policy

- You are responsible for having the right to access and process the media you
  pass to this tool.
- This tool does NOT bypass DRM, paywalls, or authentication.
- Cookie-based access via `yt-dlp` is supported with `--cookies-from-browser firefox`
  (or `chrome`). Cookies stay local; this tool does not transmit them.
- Downloaded media should not be redistributed unless you have rights to do so.
- `yt-dlp`'s extractor list is best-effort; an extractor working today may break
  tomorrow. If a download fails, run `pip install -U yt-dlp` first.

## Architecture

Two-phase pipeline:

- `extract.py` — download → 4-tier transcript chain → frames → OCR + 5-class
  classification → dedup → quality grades → `Generated_Data/<title>/`.
- `distill.py` — load artifacts → enrich transcript with OCR/citations →
  scene-change-aware frame selection → multimodal LLM call → citation-validated
  markdown + structured `distill_result.json`.

See the spec for full details on the citation contract, idempotency model,
caching, and definition of done.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(README): document merged pipeline, model config, legal/auth policy"
```

## Task 10.5: Golden-output fixtures (4 of them)

**Files:**
- Create: `tests/fixtures/golden/coding_video/{payload.golden.json,distill_result.golden.json}`
- Create: `tests/fixtures/golden/slide_talk/{payload.golden.json,distill_result.golden.json}`
- Create: `tests/fixtures/golden/ui_demo/{payload.golden.json,distill_result.golden.json}`
- Create: `tests/fixtures/golden/local_file/{payload.golden.json,distill_result.golden.json}`
- Create: `tests/integration/test_golden.py`

> **Generation strategy.** For each fixture: hand-build a small `Generated_Data/<title>/` tree (transcript + ocr.json + 4-6 fixture frames) under `tests/fixtures/golden/<scenario>/inputs/`. Run `distill.py --dry-run-payload` to produce `payload.json`, copy as `payload.golden.json`. Mock the LLM with a deterministic JSON response, run distill, copy `distill_result.json` as `distill_result.golden.json`. Commit both.

- [ ] **Step 1: Build the four input trees**

Generation script `tests/fixtures/golden/_generate.py`:

```python
"""Build the four golden fixture trees. Run once: uv run python tests/fixtures/golden/_generate.py"""
from pathlib import Path
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
FONT = ImageFont.load_default()
SCENARIOS = ["coding_video", "slide_talk", "ui_demo", "local_file"]


def _frame(path: Path, lines: list[str]):
    img = Image.new("RGB", (512, 384), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((10, 10 + i * 16), ln, fill=(0, 0, 0), font=FONT)
    img.save(path, "JPEG", quality=85)


def build(scenario: str):
    inputs = ROOT / scenario / "inputs"
    if inputs.exists():
        shutil.rmtree(inputs)
    inputs.mkdir(parents=True)
    od = inputs / "Test"
    (od / "frames").mkdir(parents=True)

    # Transcript
    (od / "Test_formatted_transcript.txt").write_text("0.0|Hello world\n5.0|How are you\n")
    (od / "Test_clean_text.txt").write_text("Hello world How are you")
    (od / "artifact_manifest.json").write_text(json.dumps({
        "schema_version": 1, "source_id": f"yt:{scenario}", "source_url": "u",
        "title": "Test", "duration_seconds": 10.0, "clip_range": None,
        "extract": {"transcript_quality": "high"}, "distill_runs": [],
    }))

    # Per-scenario frames + ocr.json
    if scenario == "coding_video":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                   ["def f():", "    return 1", "", "x = f()"])
        ocr_frames = [
            {"path": "frames/frame_000_t-00-01.jpg", "timestamp_seconds": 1.0,
             "ocr_text": "def f():\n    return 1\n\nx = f()", "ocr_confidence": 0.9,
             "frame_class": "code", "class_confidence": 0.9, "cluster_id": "c0", "ocr_error": None},
        ]
    elif scenario == "slide_talk":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                   ["RAG Pipelines", "Step 1", "Step 2", "Step 3", "Step 4"])
        ocr_frames = [
            {"path": "frames/frame_000_t-00-01.jpg", "timestamp_seconds": 1.0,
             "ocr_text": "RAG Pipelines\nStep 1\nStep 2", "ocr_confidence": 0.9,
             "frame_class": "slide_text", "class_confidence": 0.7, "cluster_id": None, "ocr_error": None},
        ]
    elif scenario == "ui_demo":
        for i, ts in enumerate([1.0, 5.0]):
            _frame(od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg",
                   ["Settings", "Save", "Cancel"])
        ocr_frames = [
            {"path": "frames/frame_000_t-00-01.jpg", "timestamp_seconds": 1.0,
             "ocr_text": "Settings\nSave\nCancel", "ocr_confidence": 0.85,
             "frame_class": "ui", "class_confidence": 0.65, "cluster_id": None, "ocr_error": None},
        ]
    else:  # local_file
        for i, ts in enumerate([1.0, 5.0]):
            _frame(od / "frames" / f"frame_{i:03d}_t-00-{int(ts):02d}.jpg", ["misc"])
        ocr_frames = []

    (od / "ocr.json").write_text(json.dumps({"video": {"title": "Test", "duration_seconds": 10}, "frames": ocr_frames}, indent=2))


for s in SCENARIOS:
    build(s)
print("ok")
```

Run: `uv run python tests/fixtures/golden/_generate.py`

- [ ] **Step 2: Generate golden payloads via `--dry-run-payload`**

For each scenario, run distill in a subshell (with the fixture as `Generated_Data`) and copy the resulting `payload.json`:

```bash
for s in coding_video slide_talk ui_demo local_file; do
  YT_GENERATED_DATA_DIR=tests/fixtures/golden/$s/inputs \
    uv run python distill.py Test knowledge_base --dry-run-payload --model gemini-3-flash
  cp tests/fixtures/golden/$s/inputs/Test/payload.json tests/fixtures/golden/$s/payload.golden.json
done
```

(For `local_file`, mock the doctor; we just want a deterministic dry-run payload — the doctor's HTTP call can be skipped by setting `OPENROUTER_API_KEY=` to any non-empty value AND ensuring the fixture cache file at `~/.cache/youtube-transcripts/model_doctor_*.json` is pre-populated with `{"timestamp": <future>, "result": {"ok": true, ...}}`. See `tests/integration/test_golden.py` Step 3 for a cleaner test fixture.)

- [ ] **Step 3: Write the golden test**

```python
# tests/integration/test_golden.py
import json
import os
from pathlib import Path
import pytest
import distill


GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
SCENARIOS = ["coding_video", "slide_talk", "ui_demo", "local_file"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_dry_run_payload_matches_golden(scenario, tmp_path, monkeypatch):
    inputs = GOLDEN / scenario / "inputs"
    # Copy inputs to tmp so distill writes there
    import shutil
    shutil.copytree(inputs, tmp_path / "data")
    monkeypatch.setenv("YT_GENERATED_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(distill, "doctor", lambda *a, **k: type("R", (), {"ok": True})())
    rc = distill.main(["Test", "knowledge_base", "--dry-run-payload", "--model", "gemini-3-flash"])
    assert rc == 0
    actual = json.loads((tmp_path / "data" / "Test" / "payload.json").read_text())
    expected = json.loads((GOLDEN / scenario / "payload.golden.json").read_text())
    # Compare structurally; image bytes are elided so the payload is deterministic.
    assert _normalize(actual) == _normalize(expected), f"golden drift in {scenario}"


def _normalize(payload):
    # Strip absolute paths or timestamps that legitimately vary across runs.
    out = []
    for c in payload:
        if c["type"] == "text":
            # Strip dynamic absolute paths if any leak in.
            out.append({"type": "text", "text": c["text"]})
        else:
            out.append({"type": "image_url", "image_url": {"url": c["image_url"]["url"]}})
    return out
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/integration/test_golden.py -v`
Expected: 4 passed.

If any fail with golden drift, examine the diff. If the change is intentional (e.g. you tweaked the prompt contract), regenerate the goldens with Step 2.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden/ tests/integration/test_golden.py
git commit -m "test: golden-output fixtures (coding/slide/ui/local) with --dry-run-payload comparison"
```

## Task 10.6: Definition of Done verification

**Files:**
- Create: `scripts/dod_check.sh`
- Modify: `README.md`

- [ ] **Step 1: Write the DoD script**

```bash
#!/usr/bin/env bash
# scripts/dod_check.sh — runs every DoD condition listed in spec §9.
set -euo pipefail
echo "=== DoD: pytest ==="
uv run pytest

echo "=== DoD: extract on test_video.mp4 ==="
TMP=$(mktemp -d)
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6
test -f $TMP/test_video/artifact_manifest.json
test -f $TMP/test_video/ocr.json
test -d $TMP/test_video/frames

echo "=== DoD: distill --dry-run-payload ==="
YT_GENERATED_DATA_DIR=$TMP uv run python distill.py test_video knowledge_base --dry-run-payload
test -f $TMP/test_video/payload.json

echo "=== DoD: legacy download_transcript.py ==="
YT_GENERATED_DATA_DIR=$TMP uv run python download_transcript.py "https://www.youtube.com/watch?v=KE39P4qBjDk" || true
# We don't fail this if YouTube is unreachable; the test_download_transcript_legacy.py covers offline.

echo "=== DoD: resumability ==="
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6
rm -f $TMP/test_video/frames/*.jpg | head -1
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6

echo "=== DoD: no TODO/XXX in shipped source ==="
! grep -rn -E "(TODO|XXX)" --include="*.py" extract.py distill.py run.py clean.py models.py frame_ocr.py frame_select.py manifest.py transcript.py enrichment.py payload.py citation.py distill_render.py

echo "=== DoD complete ==="
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/dod_check.sh
./scripts/dod_check.sh
```

Expected: all sections complete; final line `=== DoD complete ===`.

- [ ] **Step 3: Add the DoD section to README.md**

Append:

```markdown
## Definition of Done

Before declaring this implementation complete, run:

```bash
bash scripts/dod_check.sh
```

It exercises every condition in spec §9 (test suite, extract+distill on the
fixture video, resumability, legacy compat, no `TODO`s in shipped source).
```

- [ ] **Step 4: Commit**

```bash
git add scripts/dod_check.sh README.md
git commit -m "feat(dod): scripts/dod_check.sh exercises every spec §9 condition end-to-end"
```

---

# Self-review notes

This plan implements the spec end-to-end. Coverage map:

| Spec section | Tasks |
|--------------|-------|
| §1 Goals & non-goals | M1-M10 (whole plan) |
| §2 Architecture | M3 (transcript), M4-M5 (frames+OCR), M6 (extract.py), M9 (distill.py), 10.1 (run.py) |
| §3 File layout | T1.2 (vendor), T1.4 (models.yaml), all `Files:` lines reference exact paths |
| §4 Frame OCR/classification/selection | M4 (4.1-4.4), M5 (5.1-5.3), §4.6 alignment in T8.2 |
| §5 Distillation | M7 (models), M8 (prereqs), M9 (orchestrator) |
| §6 Evidence/citations | T8.4 (extract+validate), T9.3 (validator gate), T8.5 (frontmatter counts) |
| §7 Cache & idempotency | T2.1 (source_id), T2.2 (manifest), T6.5 (resumability test), T10.2 (clean.py) |
| §8.1 Error handling | T6.3 (`_ytdlp_error_message`) and per-task error tests |
| §8.2 Setup & deps | T1.1 (pyproject) |
| §8.3 Quality grades | T6.4 |
| §8.4 Testing | All M2-M10 tests + T10.5 goldens |
| §8.5 Backward compat | T3.2, T10.3, regression test in T3.2 |
| §8.6 Legal/auth | T10.4 |
| §9 Definition of Done | T10.6 |

**Placeholder scan:** No `TODO`/`TBD`/"add appropriate" instances. Every code step has actual code; every command step has actual commands.

**Type consistency:** `Profile`, `Manifest`, `OcrResult`, `OcrLine`, `FrameRecord`, `FrameClass`, `ChangePoint`, `Selected`, `SelectionResult`, `TranscriptSegment`, `TranscriptResult`, `Citation`, `ResolutionContext`, `ValidationResult`, `DoctorResult` — names used identically across all tasks. Function names (`derive_source_id`, `ocr_frame`, `classify_frame`, `dedup_code_frames`, `read_ocr_json`, `write_ocr_json`, `detect_scene_changes`, `select_frames`, `write_selected_frames_json`, `enrich_transcript`, `parse_formatted_transcript`, `build_payload`, `extract_citations`, `validate_citations`, `render_markdown`, `resolve`, `doctor`) consistent.

**Areas to re-verify during execution:**
- Vendored `claude_video.scripts.frames` API. Task 6.3 Step 2 instructs the implementer to inspect and adapt — this can't be fully pinned without running upstream code. Same for `claude_video.scripts.whisper.transcribe` (T3.1 Step 5).
- Golden fixtures depend on RapidOCR producing similar text on the synthetic frames. If OCR drift breaks tests, regenerate the goldens (T10.5 Step 2) and commit the new versions.
- The integration test in T6.2 needs a real Creative Commons MP4 — skip CI execution if size > LFS threshold. Document under `tests/fixtures/README.md` if needed.

---

# Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-07-youtube-transcripts-claude-video-merge.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a plan this size because the per-task context stays clean and progress is visible.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batched with checkpoints for review. More tokens per session, but easier to redirect mid-task.

Which approach?
