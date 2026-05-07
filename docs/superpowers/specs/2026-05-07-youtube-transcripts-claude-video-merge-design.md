# Design: youtube-transcripts + claude-video merge

**Status:** approved with revisions — review-round 2 feedback incorporated; awaiting post-revision spec review.
**Date:** 2026-05-07 (initial), revised same day.
**Author:** mdc159 (with Claude)

## Context

Two repositories with overlapping concerns:

- **`youtube-transcripts`** (this repo): YouTube transcript downloader with a 3-method fallback chain (`youtube-transcript-api` → `pytube` → `yt-dlp` captions), title-aware output paths, paragraph cleanup, and a *style transformation* layer that runs transcripts through markdown style guides via OpenRouter (`google/gemini-3-flash-preview`) into `Generated_Data/<title>/`.
- **`claude-video`** (https://github.com/bradautomates/claude-video): a Claude Code skill (`/watch`) that downloads any yt-dlp source, extracts auto-budgeted frames with `ffmpeg` (≤100 frames, ≤2 fps, duration-aware), pulls captions with Whisper (Groq/OpenAI) fallback, then has Claude `Read` each frame as an image.

The shared piece is transcript fetching. The new capability `claude-video` brings is **frames as multimodal evidence**. The goal of this merge is not transcript redundancy but to **enrich the existing distillation** — the style-transform that produces the final Obsidian-ready markdown — with visual evidence (OCR'd code spliced into the transcript at frame timestamps, plus selected non-code frames as multimodal input to a vision-capable LLM).

The principal risk is **silent degradation** — bad OCR, poor frame choice, unverifiable summaries, and "happy path passes once → declared done." The design below addresses each.

## 1. Goals & non-goals

**Goals**

- Combine transcript download + frame extraction into a single repo.
- Enrich the style-transform distillation with visual evidence:
  - OCR'd code from frames is spliced into the transcript at the matching timestamp.
  - Selected non-code frames (slides, UIs, diagrams) are sent as image input alongside the transcript to a vision-capable LLM.
- **Every claim in the output is traceable** to a transcript segment ID, frame ID, or `t=MM:SS` timestamp. Auditability is a hard requirement, not a nice-to-have.
- **Idempotent and resumable.** Re-running on the same source must skip completed work unless `--force`. Re-distilling with a different style or model must not re-download or re-OCR.
- Support YouTube + anything `yt-dlp` handles (TikTok, Vimeo, X, Loom, …) + local video files.
- Preserve full intermediate artifacts in `Generated_Data/<title>/` so re-distilling with a different style is a free, offline operation.
- Keep the LLM/model layer easy to reconfigure — vision-capable models change frequently — and *validate* configured models, not just trust profile flags.

**Non-goals**

- Do *not* repackage the result as a Claude Code skill / plugin. This stays as a personal CLI inside this repo.
- Do *not* replace the existing 3-method transcript fallback chain. Whisper is added as a 4th tier, fired only when the others fail.
- No UI, no daemon, no web server.
- No DRM bypass, no auth bypass. Cookies are user-supplied and local-only (see §8.6).

## 2. Architecture (two-phase, idempotent)

```
extract.py <url-or-path> [--out-dir DIR] [--max-frames N] [--start T] [--end T]
                         [--no-frames] [--keep-video] [--force] [--force-ocr]
                         [--cookies-from-browser BROWSER]
  ├─ resolve source → derive stable source_id (§7)
  ├─ check artifact_manifest.json — skip completed steps unless --force
  ├─ get title (yt-dlp --get-title; for local files: filename stem)
  ├─ fetch transcript (chain): yt-transcript-api → pytube → yt-dlp captions → Whisper
  ├─ download video (yt-dlp) → media_cache/<source_id>/video.<ext>
  ├─ extract frames (vendored frames.py)
  ├─ OCR every frame with confidence gating (RapidOCR)
  ├─ classify each frame: code | slide_text | ui | diagram | other (§4.3)
  ├─ deduplicate near-identical OCR clusters (§4.5)
  ├─ score quality (transcript, ocr, frame coverage) → extract_meta.json
  ├─ update artifact_manifest.json
  └─ write Generated_Data/<title>/

distill.py <title-or-dir> <style> [--model PROFILE] [--max-vision-frames N]
                                  [--token-budget T] [--dry-run-payload] [--force]
  ├─ load transcript, ocr.json, manifest from Generated_Data/<title>/
  ├─ resolve model profile (CLI / env / models.yaml default)
  ├─ run model capability check (§5.2) — fail fast if profile is broken
  ├─ select frames (scene-change-aware + even-spacing fallback, §4.4)
  ├─ build enriched_transcript.md (insertion rule, §4.6)
  ├─ build multimodal payload + distillation prompt contract (§5.5)
  ├─ if --dry-run-payload: write payload.json and exit
  ├─ call provider; capture token usage and warnings
  ├─ render distill_result.json (structured) → render markdown from it
  └─ write Generated_Data/<title>/<title>_<style>.md + distill_result.json

run.py <url-or-path> <style>          # convenience: extract → distill in one shot

models.py doctor --profile <name>     # validates key, text request, image request
clean.py [--delete-video] [--delete-frames] [--keep-ocr] [--older-than 30d] [--dry-run]
```

## 3. Components & file layout

| Path | Status | Role |
|------|--------|------|
| `vendor/claude_video/scripts/download.py` | new (vendored) | yt-dlp wrapper |
| `vendor/claude_video/scripts/frames.py` | new (vendored) | ffmpeg + auto-fps |
| `vendor/claude_video/scripts/transcribe.py` | new (vendored) | caption parsing + Whisper orchestration |
| `vendor/claude_video/scripts/whisper.py` | new (vendored) | Groq / OpenAI clients |
| `vendor/claude_video/scripts/setup.py` | new (vendored) | ffmpeg/yt-dlp preflight |
| `extract.py` | new | Phase 1 orchestrator (idempotent) |
| `frame_ocr.py` | new | RapidOCR + 5-class classifier + dedup |
| `frame_select.py` | new | Scene-change detector (perceptual hash) + even-spacing fallback |
| `distill.py` | new | Phase 2 — multimodal LLM call + structured output |
| `models.py` | new | Profile resolution, capability validation (`doctor` subcommand) |
| `clean.py` | new | Storage management |
| `run.py` | new | Convenience wrapper for one-shot extract → distill |
| `models.yaml` | new | Provider/model profiles (§5.1) |
| `download_transcript.py` | kept | Legacy entrypoint — preserved with tests (§9 DoD). Delegates to `extract.py`/`run.py`. |
| `transform_transcript.py` | refactored | Text-only fallback used by `distill.py` when active profile fails capability check or has `vision: false`. |
| `styles/*.md` | kept | Unchanged (out of scope to make vision-aware in this merge) |
| `media_cache/<source_id>/video.<ext>` | new | Downloaded video. Default: deleted after extract finishes unless `--keep-video`. |
| `Generated_Data/<title>/*_formatted_transcript.txt` | kept | Existing |
| `Generated_Data/<title>/*_clean_text.txt` | kept | Existing |
| `Generated_Data/<title>/<title>_<style>.md` | kept (format extended) | Existing markdown output, with citations (§6) |
| `Generated_Data/<title>/<title>_<style>.distill_result.json` | new | Structured sidecar output (§5.6) |
| `Generated_Data/<title>/<title>_enriched_transcript.md` | new | Timestamped transcript with OCR'd code spliced in. Reused on subsequent distill runs. |
| `Generated_Data/<title>/frames/` | new | `frame_NNN_t-MM-SS.jpg`, plus `selected_frames.json` listing what `distill.py` picked and why |
| `Generated_Data/<title>/ocr.json` | new | Per-frame text, confidence, classification, dedup cluster ID |
| `Generated_Data/<title>/extract_meta.json` | new | Source URL, duration, frame budget used, transcript source, **quality grades** (§8.3) |
| `Generated_Data/<title>/artifact_manifest.json` | new | Manifest of every generated file with hashes, command args, model profile, OCR/dedup version, prompt-contract version |
| `Generated_Data/<title>/payload.json` | new (when `--dry-run-payload`) | Exact LLM payload that *would* be sent. No API call made. |

## 4. Frame OCR, classification, and selection

### 4.1 Library

`rapidocr-onnxruntime`. Python-only install via `uv add`, no system dependencies. Pinned to a tested range in `pyproject.toml` and re-tested on each Python upgrade (§8.2). Rejected `pytesseract` (system tesseract dep).

### 4.2 Per-frame run with confidence gating

For each `frame_NNN_t-MM-SS.jpg`:

1. RapidOCR returns `[(bbox, text, confidence), ...]`.
2. Concatenate text in reading order; record per-line confidence and a frame-level mean.
3. **Confidence gate.** Lines with `confidence < 0.5` are kept in raw OCR but excluded from the "high-confidence text" used for classification and from injected code blocks. Low-confidence injections get a `~approximate` marker (§6).
4. Run the 5-class classifier (§4.3).
5. Run dedup clustering across the per-video frame set (§4.5).
6. Append to `ocr.json`.

### 4.3 Classification (5-class)

`is_code_heavy` (boolean) is replaced by `class ∈ {code, slide_text, ui, diagram, other}` plus `class_confidence ∈ [0,1]`.

| Class | Heuristic signals (any 2 trigger) | Distill-time treatment |
|-------|------------------------------------|------------------------|
| `code` | code-glyph density `≥ 3 per 100 chars` of `{[]<>(){};=`; indentation pattern (≥3 lines start with 2+ spaces or tab); keywords (`def`, `function`, `class`, `import`, `const`, `if (`, `// `, `# `); line uniformity (≥5 lines monospace-ish) | OCR text spliced into enriched transcript as fenced ` ```code ` block at the frame's timestamp. **Excluded** from vision payload. |
| `slide_text` | high text density, low code-glyph density, often centered/large bbox, often title-case lines | OCR text inlined as a quoted slide-note at the timestamp: `> [slide t=MM:SS] …`. Frame *also* eligible for vision payload if it contains layout/diagrams. |
| `ui` | recognizable UI strings (`Submit`, `Settings`, `Login`, button-like short labels), low overall text density | Short OCR caption + frame attached to vision payload. |
| `diagram` | low OCR text density, classifier marks remaining content as visually complex (heuristic: large bbox area uncovered by text) | Vision-only. No OCR injection. |
| `other` | none of the above hit threshold | Default: even-spacing eligible for vision; OCR text not injected. |

**False positives are not free.** The previous "false positives are cheap" assumption is rejected. Each class has its own markdown wrapper so a misclassified slide is not formatted as executable code.

When confidence in classification is low (`class_confidence < 0.6`), the frame is treated as `other` to err on the side of not making strong claims about its content.

### 4.4 Frame selection for vision (scene-change-aware)

Even spacing is the *fallback*, not the primary. Real videos concentrate information at scene/slide/code transitions.

Algorithm (in `frame_select.py`):

1. Compute a perceptual hash (`imagehash.phash`) for every extracted frame.
2. Compute Hamming distance between consecutive frames.
3. Identify "change points" where distance exceeds an adaptive threshold (default: median + 1.5×MAD).
4. For each change point, select the frame *just after* the transition (the new state).
5. If selection underflows the budget, fill with even-spacing across remaining gaps.
6. **Always exclude `code`-class frames** — their content is in the transcript already.
7. **Token-budget-aware cap.** Final count = `min(--max-vision-frames, token_budget // est_image_tokens(resolution))`. Default `--max-vision-frames 16`; a `--token-budget T` flag overrides to a hard total budget. Per-provider/per-model image limits (OpenRouter notes vary) are respected from `models.yaml` (§5.1).

Selected frames are recorded to `selected_frames.json` with the reason (`scene_change@t=01:23` or `even_spacing@t=03:45`) for auditability.

### 4.5 OCR deduplication for code-heavy frames

A 20-minute coding video can have dozens of frames showing essentially the same code block. Naive injection bloats the transcript and confuses the LLM.

1. For all frames classified `code`, compute a normalized fingerprint of OCR text (whitespace collapsed, case preserved, comments and trailing punctuation stripped).
2. Cluster frames with fingerprint similarity ≥ 0.85 (rapidfuzz token-set ratio).
3. Within a cluster, keep only frames where the OCR text *changes* — i.e. the first frame of the cluster, plus any frame whose fingerprint diverges enough to break the cluster.
4. Each cluster gets a `cluster_id`; `ocr.json` records both the per-frame text and `cluster_id` so distill can reason at cluster level.

The enriched transcript injects only **changed** code blocks. Cluster representatives carry timestamp ranges (e.g. `code shown 02:15–03:40`) rather than repeated identical fences.

### 4.6 Transcript-frame alignment (insertion rule)

Use `*_formatted_transcript.txt` as the source (timestamped). For each frame to inject:

1. Find the transcript segment whose `[start, end]` contains `frame.timestamp_seconds`. Insert the frame's OCR/note **immediately after** that segment.
2. If no segment contains the timestamp (e.g. silence), insert between the segments whose `end < t` and `start > t` (sorted boundary).
3. If `--start` / `--end` was used at extract time, frame timestamps remain absolute (real video timeline), and segment lookup uses absolute times. Tested explicitly in §8.4.

The result is `<title>_enriched_transcript.md` — a sidecar artifact that survives across distill runs, so re-styling is cheap.

## 5. Distillation: model config, validation, and structured output

### 5.1 Reconfigurable model layer

All model config in **`models.yaml`** at the repo root:

```yaml
default: gemini-3-flash

profiles:
  gemini-3-flash:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3-flash-preview
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 16          # provider/model hint, validated by `doctor`
    max_image_bytes: 5242880

  gemini-3-pro:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3-pro
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 32

  claude-sonnet-4-6:
    base_url: https://openrouter.ai/api/v1
    model: anthropic/claude-sonnet-4-6
    vision: true
    reasoning: false
    api_key_env: OPENROUTER_API_KEY
    max_images: 20

  gpt-4o:
    base_url: https://api.openai.com/v1
    model: gpt-4o
    vision: true
    reasoning: false
    api_key_env: OPENAI_API_KEY
    max_images: 10
```

**Resolution order:** CLI flag (`--model gemini-3-pro`) → env var (`DISTILL_MODEL=gemini-3-pro`) → `models.yaml` `default`. Adding a new model = one YAML entry, zero code changes.

### 5.2 Capability validation (`models.py doctor`)

Static `vision: true/false` is not enough. Models drift, providers change behavior, keys expire. `models.py doctor --profile X` runs a real check before trusting a profile:

1. Verify `api_key_env` is set in env or `.env`.
2. Send a 5-token text request; assert non-empty response.
3. If profile claims `vision: true`, send a request with one 32×32-pixel fixture image (committed to `tests/fixtures/`); assert no schema error and a non-empty response.
4. If profile claims `reasoning: true`, send a request with `extra_body={"reasoning": {"enabled": True}}`; assert no schema error.
5. Report `OK` / a structured failure (which probe failed and the provider's error).

`distill.py` calls a cached version of `doctor` automatically the first time a profile is used in a given hour (results cached to `~/.cache/youtube-transcripts/model_doctor_<profile>_<hash>.json`). Failed validation falls back to the text-only path (`transform_transcript.py` semantics) and records a warning in `distill_result.json`.

### 5.3 Payload construction

OpenAI SDK shape; works for OpenRouter, OpenAI, and Anthropic-via-OpenRouter:

```python
content = [
    {"type": "text", "text": SYSTEM_PROMPT_CONTRACT + "\n\n" + style_content + "\n\n---\n\n# Transcript (OCR-enriched, citation-tagged)\n\n" + enriched_transcript},
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},  # × selected frames
]
```

Each image block carries an HTML comment marker preceding its base64 payload in the constructed message — `<!-- frame_NNN_t-MM-SS -->` — so the model is encouraged to cite by frame ID. (Provider-side image blocks don't always preserve adjacent text, so the same frame ID is also restated in the text block as a `Visual evidence index:` table.)

### 5.4 Transcript enrichment

For each `code`-class cluster representative at timestamp range `[T1, T2]`, the transcript becomes:

````
[t=01:23–03:40 | seg #45] (spoken text from transcript across that range)

```code-from-frame_037_t-01-23 [cluster_id=c4]
(deduplicated OCR'd code text, marker ~approximate if any line < 0.5 confidence)
```
````

For `slide_text` frames:

```
[t=05:12 | seg #112 | frame_088_t-05-12] (spoken text)

> [slide] OCR'd slide text here (~approximate if low-confidence lines present)
```

`ui` and `diagram` frames are referenced inline with their frame ID but their content is delegated to the vision payload.

### 5.5 Distillation prompt contract

`SYSTEM_PROMPT_CONTRACT` is a versioned string in `prompts/distill_contract_vN.md` (referenced by version number in `artifact_manifest.json`). It enforces:

1. **No unsupported claims.** Every technical statement, step, code snippet, UI observation, or diagram interpretation in the output must cite a transcript segment (`seg #N`), a frame (`frame_NNN`), or a timestamp range (`t=MM:SS`). Statements without citation are forbidden.
2. **Preserve uncertainty.** When OCR is marked `~approximate`, downstream code blocks must inherit the marker. When transcript quality is `low` (§8.3), the model must say so in the output's quality note.
3. **Separate sections.** Output must contain at least: `## Summary`, `## Key Points`, `## Steps / Walkthrough` (when applicable), `## Code` (when applicable), `## Tools & References`, `## Visual Evidence Used`, `## Open Questions`. Each section's contents are individually citable.
4. **No hallucinated visual content.** Do not infer text from a frame that is in the vision payload but has no OCR. If you describe a frame, prefix it with `frame_NNN observation:` so the claim is auditable.
5. **Style guide overlay.** The user-supplied style guide (e.g. `coding_agent.md`) shapes tone and structure but does *not* override the citation requirement.

The prompt-contract version is recorded in both `artifact_manifest.json` and the output frontmatter.

### 5.6 Output: markdown + structured sidecar

**`distill_result.json`** is the canonical output. The markdown is rendered from it.

```json
{
  "schema_version": 1,
  "source_id": "yt:KE39P4qBjDk",
  "title": "How_to_Build_a_RAG_Pipeline",
  "model_profile": "gemini-3-flash",
  "prompt_contract_version": 3,
  "summary": "...",
  "key_points": [{"text": "...", "citations": ["seg#45", "frame_037_t-01-23"]}],
  "steps": [{"order": 1, "text": "...", "citations": ["seg#67"]}],
  "code_blocks": [{"language": "python", "code": "...", "citations": ["frame_037_t-01-23", "cluster_id=c4"], "approximate": false}],
  "tools_mentioned": [{"name": "FAISS", "citations": ["seg#102"]}],
  "open_questions": ["..."],
  "visual_evidence_used": [{"frame_id": "frame_088_t-05-12", "class": "diagram", "interpretation": "...", "selection_reason": "scene_change"}],
  "quality": {"transcript": "high", "ocr": "medium", "frame_coverage": "high", "distillation_confidence": "medium"},
  "warnings": ["whisper fallback used; transcript may have minor errors"],
  "token_usage": {"prompt": 12450, "completion": 2100, "image_count": 12}
}
```

The markdown file is rendered from this JSON by a deterministic template (`distill_render.py`). This means downstream consumers (Obsidian, RAG ingestion, search index) can read the JSON directly without parsing markdown.

### 5.7 `--dry-run-payload`

Exits before the API call; writes the exact payload (with image bytes elided to file refs) to `Generated_Data/<title>/payload.json`. Useful for golden tests, debugging prompt-contract changes, and estimating token cost without spending it.

## 6. Evidence model and citations

A first-class concept, not a footnote.

**Citation tokens** that may appear in any output text:

- `seg#NNN` — transcript segment ID (segments numbered sequentially in `*_formatted_transcript.txt` after parsing).
- `frame_NNN` — short form of `frame_NNN_t-MM-SS`.
- `frame_NNN_t-MM-SS` — fully-qualified frame ID with timestamp.
- `cluster_id=cN` — OCR dedup cluster (groups equivalent code-frame OCR).
- `t=MM:SS` or `t=MM:SS–MM:SS` — bare timestamp / range when no specific artifact applies.

**Citation validator** (`distill.py` post-step): parses the rendered markdown, extracts all citations, verifies each one resolves to a real artifact (segment exists, frame file exists, cluster exists). Unresolved citations cause distill to fail with a structured error listing each one. This catches both LLM-fabricated citations and bugs in our own rendering.

**Frontmatter** of `<title>_<style>.md` always includes:

```yaml
citations:
  segments_referenced: 87
  frames_referenced: 12
  unresolved: 0
quality:
  transcript: high
  ocr: medium
  frame_coverage: high
  distillation_confidence: medium
prompt_contract_version: 3
model_profile: gemini-3-flash
```

If `unresolved > 0`, the file gets a banner at the top noting the issue.

## 7. Cache, idempotency, and storage

### 7.1 `source_id`

A stable identifier per source, derived deterministically:

| Source type | `source_id` |
|-------------|-------------|
| YouTube URL | `yt:<video_id>` |
| TikTok / Vimeo / X / Loom | `<platform>:<id>` from yt-dlp's extractor info |
| Other yt-dlp source | `web:<sha1(canonical_url)[:12]>` |
| Local file | `local:<sha1(absolute_path)[:12]>` |

If `--start` / `--end` was used, the source_id is suffixed (`yt:abc123#15-45`). This means the same video at different clip ranges is treated as distinct artifact sets.

### 7.2 `artifact_manifest.json`

Authoritative record of what's been done for this source:

```json
{
  "schema_version": 1,
  "source_id": "yt:KE39P4qBjDk",
  "source_url": "https://...",
  "title": "How_to_Build_a_RAG_Pipeline",
  "duration_seconds": 612,
  "clip_range": null,
  "extract": {
    "command_args": ["...", "--max-frames", "60"],
    "completed_at": "2026-05-07T10:31:02Z",
    "transcript_source": "yt-dlp-captions",
    "transcript_quality": "high",
    "frame_budget_used": 58,
    "ocr_version": "rapidocr-1.4.4",
    "dedup_version": 1,
    "files": {
      "formatted_transcript": {"path": "...", "sha256": "..."},
      "clean_text": {"path": "...", "sha256": "..."},
      "ocr_json": {"path": "...", "sha256": "..."},
      "frames_dir": {"path": "...", "frame_count": 58}
    }
  },
  "distill_runs": [
    {
      "style": "coding_agent",
      "model_profile": "gemini-3-flash",
      "prompt_contract_version": 3,
      "completed_at": "2026-05-07T10:34:18Z",
      "token_usage": {...},
      "files": {
        "markdown": {"path": "...", "sha256": "..."},
        "distill_result_json": {"path": "...", "sha256": "..."}
      }
    }
  ]
}
```

### 7.3 `--force` semantics

| Step | Skipped if… | Forced re-run by… |
|------|-------------|-------------------|
| Download video | `media_cache/<source_id>/video.<ext>` exists *and* manifest records same args | `extract.py --force` |
| Transcript fetch | manifest records a successful transcript for this `source_id` and clip range | `extract.py --force` |
| Frame extraction | manifest records a frame budget ≥ requested for same clip range | `extract.py --force` |
| OCR | manifest records same `ocr_version` over the same frame set | `extract.py --force-ocr` |
| Distill | a `distill_runs` entry exists with same style + model + prompt_contract_version | `distill.py --force` |

Partial recovery: if any single step's output is missing or its hash mismatches, that step re-runs even without `--force` (treated as corrupted artifact).

### 7.4 Storage separation

- `media_cache/<source_id>/` — heavyweight artifacts (downloaded video). Default: video is **deleted** after extract finishes unless `--keep-video`. The frames extracted from it survive in `Generated_Data/`.
- `Generated_Data/<title>/` — everything the user might want to re-read or re-distill: transcripts, OCR JSON, frames, manifest, enriched transcript, markdown outputs, distill result JSONs.

This split means a user with limited disk can run `clean.py --delete-video --older-than 7d` without losing the artifacts that drive distillation.

### 7.5 `clean.py`

```
clean.py [--delete-video] [--delete-frames] [--keep-ocr]
         [--older-than DURATION] [--source-id ID] [--title PATTERN]
         [--dry-run]
```

Default behavior: dry-run, lists what would be deleted with sizes. Requires `--apply` to actually delete. Targets:

- `--delete-video` — drop everything in `media_cache/`.
- `--delete-frames` — drop `Generated_Data/*/frames/` (keeps OCR JSON, transcripts, markdown).
- `--keep-ocr` — modifies `--delete-frames` to keep `ocr.json` (default behavior anyway, but explicit).
- `--older-than 30d` — restrict to artifacts whose manifest `completed_at` is older than 30 days.
- `--dry-run` (default) / `--apply`.

## 8. Operational details

### 8.1 Error handling & failure modes

| Failure | Behavior |
|---------|----------|
| `yt-dlp` cannot reach source — extractor not found | Print yt-dlp error; tell user `yt-dlp` extractors evolve and ours may be outdated; suggest `pip install -U yt-dlp`. Exit 1. |
| `yt-dlp` cannot reach source — geo-block / age-gate / login | Detect typical stderr patterns; print a focused message: source needs cookies (`--cookies-from-browser` flag passed through to yt-dlp) or is unavailable in this region. Do not bypass. Exit 1. |
| `yt-dlp` cannot reach source — playlist URL when single video expected | Detect; print "this URL is a playlist, pass a specific video URL or use yt-dlp directly to enumerate." Exit 1. |
| `yt-dlp` rate-limited (429) | Print "rate-limited; retry later"; do not auto-retry. Exit 1. |
| `yt-dlp` cannot reach source — private/deleted | Surface yt-dlp stderr; exit 1. |
| All transcript methods (incl. Whisper) fail | Continue extraction; write `clean_text.txt` with header note `# transcript_unavailable`. Set `transcript_quality: none` in extract_meta. Distill runs frames-only with a strong banner. |
| `ffmpeg` / `yt-dlp` missing | Run `setup.py --check`; print platform install command; exit 2. |
| RapidOCR fails on a single frame | Log warning; write empty OCR result with `ocr_error`; continue. |
| RapidOCR fails to import (Python version mismatch) | Print pinned-range error; exit 2. |
| Profile in `models.yaml` not found | List available profiles; exit 1. |
| `models.py doctor` fails | If called directly, print the failure and exit 1. If called from `distill.py`, fall back to text-only path and record warning. |
| Provider API call fails mid-distill | Print error; exit 1. No retry in v1. |
| Provider returns empty content | Raise `ValueError`. |
| Vision frames present but profile has `vision: false` | Drop image blocks; send text-only; record warning in `distill_result.json`. |
| Citation validator finds unresolved citations | `distill.py` exits 1; output files written but flagged. User must re-run or review. |

### 8.2 Setup & dependencies

**Python deps** (added to `pyproject.toml`):

- `rapidocr-onnxruntime` (pinned to a tested range, e.g. `>=1.4,<2.0`)
- `pillow` (image handling, base64)
- `pyyaml` (`models.yaml`)
- `imagehash` (perceptual hashing for scene-change detection)
- `rapidfuzz` (OCR dedup similarity)

**Python version:** Pin to `>=3.10,<3.13` initially (`rapidocr-onnxruntime` packaging has historically had Python-version friction). Re-test on each Python upgrade as a CI gate.

**System deps** (existing): `ffmpeg`, `yt-dlp`. Vendored `setup.py` detects them.

**API keys:**

- `OPENROUTER_API_KEY` — required for default profile.
- `GROQ_API_KEY` *or* `OPENAI_API_KEY` — required only when Whisper fallback fires.
- Per-profile keys via `api_key_env` in `models.yaml`.

### 8.3 Quality grades in `extract_meta.json`

Three grades, computed at extract time, stored alongside the file paths:

- `transcript_quality` ∈ {`high`, `medium`, `low`, `none`}
  - `high` — captions returned by youtube-transcript-api or yt-dlp captions, language match.
  - `medium` — Whisper fallback used, or captions via pytube (less reliable parsing).
  - `low` — Whisper but audio under 30 dB SNR or duration > 25-min upload limit hit.
  - `none` — no transcript at all.
- `ocr_quality` ∈ {`high`, `medium`, `low`, `none`}
  - Mean per-frame confidence: ≥0.85 high, 0.65–0.85 medium, <0.65 low. `none` if no frames.
- `vision_frame_coverage` ∈ {`high`, `medium`, `low`} based on (selected_non_code_frames / duration_minutes).

A fourth grade, `distillation_confidence`, is computed at distill time as a function of the three above plus citation density and `unresolved_citations`. Recorded in `distill_result.json`.

### 8.4 Testing

**Unit:**

- `frame_ocr.py` classifier against a 15-frame fixture set (3 IDE/code, 3 slides, 3 UI, 3 diagrams, 3 mixed/other) committed to `tests/fixtures/`.
- `frame_ocr.py` deduplication: synthetic OCR-text inputs assert correct cluster grouping and representative selection.
- `frame_select.py`: deterministic perceptual-hash deltas yield expected change points; budget cap respected; even-spacing fallback fires when changes < budget.
- `models.py` profile resolution (CLI > env > default; missing profile errors).
- `models.py doctor`: mocked HTTP fixtures cover all probe outcomes.
- `distill.py` payload builder against fake `ocr.json` + transcript: assert correct injection rule, base64 frame count matches budget, citation tags present.
- Citation validator: assert resolution and that fabricated citations cause errors.

**Integration:**

- `extract.py` against a 30-second public-domain test video committed to `tests/fixtures/test_video.mp4` — assert all expected files land, hashes recorded.
- `extract.py` resumability: run, delete one artifact, re-run without `--force` → only the missing artifact is rebuilt.
- `--start` / `--end` clipping: assert that absolute timestamps survive in `ocr.json` and selected frames.

**Golden-output:**

Four short fixtures (≤60s each), each with a recorded `payload.json` and `distill_result.json`:

1. Coding tutorial fixture (IDE shots).
2. Slide-talk fixture.
3. UI-demo fixture (clicks/transitions).
4. Local file fixture (no captions, Whisper required).

Tests assert that `--dry-run-payload` produces a byte-identical payload to the golden, modulo timestamps. The provider call itself is mocked.

### 8.5 Backward compatibility

- `download_transcript.py <url>` (no style) — unchanged behavior, transcript-only output. Internally calls `extract.py --no-frames`. Tested explicitly in §9 DoD.
- `download_transcript.py <url> <style>` — delegates to `run.py`. Output paths unchanged.
- `transform_transcript.py` — kept and refactored; used as text-only fallback. No external behavior change.
- Existing files in `Generated_Data/<title>/` keep their current names. New files are additive.

### 8.6 Legal / authentication notes (README)

The merged tool's README must include a short policy section:

- The user is responsible for having rights to access and process the media.
- The tool does not bypass DRM, paywalls, or authentication.
- Cookie-based access (via `yt-dlp --cookies-from-browser`) is supported but cookies stay local and are never logged or transmitted by this tool.
- Downloaded media should not be redistributed unless the user has rights to do so.
- yt-dlp's site list is best-effort; an extractor working today may break tomorrow.

This is a docs-only deliverable but treated as part of done.

## 9. Definition of done

The implementation is **not** done when scripts are wired together. Done means:

1. **`uv run pytest` passes** including all four golden-output fixtures.
2. **`extract.py` works end-to-end** on the committed 30-second public-domain test video, producing every expected file with valid manifest entries.
3. **`distill.py --dry-run-payload`** produces byte-identical payloads to golden fixtures (timestamps modulo).
4. **`run.py` works text-only** when the active profile fails its `doctor` check (validates the fallback path).
5. **`models.py doctor --profile gemini-3-flash`** passes against a real OpenRouter key (manual run, documented in README).
6. **Resumability:** delete any one artifact in `Generated_Data/<title>/`, re-run `extract.py` without `--force`, only the missing artifact rebuilds.
7. **Citation validator:** an integration test that injects a fabricated `seg#9999` reference into the LLM mock causes `distill.py` to exit 1.
8. **Legacy preserved:** `download_transcript.py <url>` (no style) produces byte-identical output to the pre-merge version on a fixture URL. Tested.
9. **README examples** are exact and runnable from a clean clone after `uv sync`.
10. **No `TODO` or `XXX`** in shipped source.

A coding agent that wires scripts together and reports the happy path passes is **not** done. All ten conditions must hold.

---

## Appendix A — Decision log

This log captures every brainstorming question, the options presented, the option chosen, and the reasoning. Useful when revisiting decisions later.

### A.1 — Use cases the combined tool should serve

**Options presented:** coding tutorials → on-screen code; slide decks → slide text + diagrams; UI/product demos → on-screen description; richer summaries grounded in visuals.

**Chosen.** "Anything relevant that would enrich the distillation."

**Why.** Frames are not for a single use case; they are general-purpose evidence feeding the existing style-transform pipeline. The pipeline (transcript → style guide → markdown) stays at the centre.

### A.2 — How `claude-video` physically lives in the repo

**Options:** vendor at `vendor/claude_video/`; submodule; fork; install as Claude skill.

**Chosen.** Vendor at `vendor/claude_video/`.

**Why.** Easiest to modify when adapting (programmatic calls instead of skill harness). Submodule rejected (Python imports across submodule boundary are awkward). Fork rejected (no real gain over vendor). Skill installation rejected (user wanted in-repo).

### A.3 — How frames reach the distillation step

**Options:** OCR-everything-into-transcript; multimodal-vision-only; hybrid (OCR for code, vision for rest); save-for-later only.

**Chosen.** Hybrid.

**Why.** Pure OCR misses diagram/UI semantics. Pure vision is expensive and overkill for code (OCR is deterministic and cheap there). Hybrid puts each frame on the cheapest path that captures its information. Save-for-later was rejected because the user wants the *distillation itself* enriched.

### A.4 — Input sources to support

**Options:** YouTube only; YouTube + local; anything yt-dlp + local.

**Chosen.** Anything yt-dlp + local.

**Why.** Maximum surface but matches "anything relevant that would enrich the distillation." Whisper fallback is required to make this work for caption-less sources.

### A.5 — Output retention

**Options:** keep everything; keep transcript + markdown only; keep markdown only.

**Chosen.** Keep everything (with §7.4 storage split between `media_cache/` and `Generated_Data/` to keep the heavy bits separable).

**Why.** Re-styling is the user's downstream pattern. Storage cost is acceptable.

### A.6 — Top-level structure

**Options:** two-phase pipeline; single-command merge; skill packaging; hybrid (two-phase modules under one default command).

**Chosen.** Two-phase.

**Why.** Re-styling should be free. Each phase has clear responsibility. `run.py` exists as the convenience wrapper for the one-shot case.

### A.7 — Late-stage user feedback: model reconfigurability

**Trigger.** *"Make being able to reconfigure the LLMs not too difficult, as the ones with vision kind of change day by day."*

**Decision.** Centralise model config in `models.yaml`. Resolution order CLI → env → file default. New model = one YAML entry, zero code changes. `vision: bool` per profile *plus* runtime capability validation (§5.2) since static flags are not enough.

### A.8 — Minor design decisions

| Decision | Rationale |
|----------|-----------|
| RapidOCR over pytesseract | No system dependency; pure-Python install. |
| Frame timestamps remain absolute under `--start`/`--end` | Citations align with the original video timeline. Tested in §8.4. |
| `download_transcript.py` kept as legacy entrypoint | Backward compat. Tested in §9 DoD. |

### A.9 — Review-round 2 additions (from user post-draft critique)

The user reviewed the v1 spec and approved the architecture but flagged ten gaps that needed promotion from "nice to have" to "main design" before the spec could be called implementation-ready. All ten are now folded into the main sections.

| # | Issue raised | Resolution in this spec |
|---|--------------|-------------------------|
| 1 | No explicit evidence model — output may not be auditable | §6 added as a first-class section. Citation validator runs as a `distill.py` post-step. Frontmatter records citation counts and `unresolved` count. |
| 2 | Idempotency and cache were Appendix B (TBD) | §7 added as main design. `source_id`, `artifact_manifest.json`, granular `--force` semantics, partial-recovery on hash mismatch. |
| 3 | Even-spacing frame selection misses the useful frames | §4.4 — perceptual-hash scene-change detector primary; even-spacing is fallback. Token-budget aware (`--token-budget`). |
| 4 | Static `vision: true/false` is not enough | §5.2 — `models.py doctor` runs real probes (text, optional 32×32 image, optional reasoning flag). Cached for an hour. Distill auto-falls-back on failure. |
| 5 | OCR can be subtly wrong; "false positives are cheap" was wrong | §4.2 confidence gating; §4.3 5-class classifier with class-specific markdown wrappers; §4.5 dedup clustering on code frames. `~approximate` markers propagate. |
| 6 | Transcript alignment was hand-wavy | §4.6 explicit insertion rule (segment containing frame timestamp; or boundary insertion). Tested in §8.4. |
| 7 | Failure on missing transcript was too soft | §8.1 frames-only path now sets `transcript_quality: none` and writes a strong banner; §8.3 quality grades make the degradation visible to downstream consumers. |
| 8 | yt-dlp breadth = operational hazard | §8.1 specific handling for cookies/auth, geo/age-gate, playlists, rate-limits, extractor breakage. |
| 9 | Legal/ToS boundary missing | §8.6 README policy section is part of done. |
| 10 | Storage will accumulate; "keep everything" was incomplete | §7.4 `media_cache/` vs `Generated_Data/` split; §7.5 `clean.py` with dry-run-by-default and granular flags. |
| 11 | Python version pin missing for RapidOCR | §8.2 explicit pin and CI gate. |
| 12 | Tests were too thin | §8.4 expanded to include four golden-output fixtures and resumability tests. |
| 13 | Distillation prompt was not contractual | §5.5 versioned `SYSTEM_PROMPT_CONTRACT` with five enforced rules; version recorded in manifest. |
| 14 | Markdown-only output blocks reuse | §5.6 structured `distill_result.json` is canonical; markdown rendered from it. |
| 15 | "Done" was undefined | §9 ten-condition Definition of Done. Coding agent cannot declare success on happy-path-once. |

## Appendix B — Open questions / things to revisit

These remain non-blocking and intentionally deferred:

- **Whisper key prompt UX.** When Whisper is needed but no key is configured, current design exits with a clear message. Revisit if it feels noisy in practice; could add an `AskUserQuestion`-style interactive flow for skill use, but not for CLI.
- **Style-guide vision-awareness.** Existing `styles/*.md` were written for text-only input. A follow-up pass could rewrite them to leverage visual evidence. Out of scope for this merge.
- **Retry/backoff on provider API failures.** None in v1. Add later if rate-limit failures become common.
- **Multi-language OCR.** RapidOCR supports several languages; current config assumes the dominant transcript language is also the OCR language. Multi-lang handling is a future enhancement.
- **Cookies passthrough beyond the basic flag.** `--cookies-from-browser` is in v1 (see §2 args). A future enhancement could add per-source cookie file persistence so users don't re-enter browser selection per run.
