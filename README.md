# YouTube Transcripts

Turn a YouTube URL or local video into a citation-grounded, multimodal artifact for an agent workflow. The pipeline pulls a transcript, extracts and OCRs visual evidence, classifies what's on screen (code / slide / UI / diagram), routes the content to the best skill-style workflow, then sends an enriched payload to a vision-capable LLM where every claim cites a transcript segment, frame, cluster, or timestamp.

## How it works

Two phases, written so you can re-route or re-style without re-downloading:

```
extract.py  ─►  Generated_Data/<title>/  ─►  distill.py
   │           transcript + frames +          │
   │           ocr.json + manifest            ▼
   │                                     <title>_<style>.md
   ▼                                     <title>_<style>.distill_result.json
download → 4-tier transcript chain
       → ffmpeg frame extraction
       → RapidOCR + 5-class classifier
       → near-duplicate code-frame clustering
       → optional style router
       → quality grades + extract_meta.json
```

`extract.py` is idempotent — re-running skips work whose outputs are still intact. `distill.py` can use an explicit style or `auto`, which builds a lightweight video profile from transcript and OCR signals, picks `coding_agent`, `diy_project`, or `knowledge_base`, runs style-aware frame selection, builds a multimodal payload, validates the model can actually do what its profile claims (`doctor`), then calls the LLM and validates every citation in the response. `run.py` chains both for one-shot use.

## Install

Requires Python 3.11–3.12 (the lower bound is forced by `rapidocr-onnxruntime` wheels), [uv](https://docs.astral.sh/uv/), and `ffmpeg`/`ffprobe` on PATH.

```bash
uv sync
```

Set an API key for whichever model profile you want to use. The default profile (`gemini-3-flash`) reads `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY=sk-or-...
# or put it in .env
```

## Usage

### One-shot

```bash
uv run python run.py "https://www.youtube.com/watch?v=KE39P4qBjDk" coding_agent
uv run python run.py "https://www.youtube.com/watch?v=KE39P4qBjDk" auto
```

Downloads, extracts frames + OCR, and distills with either an explicit style or the router. Available styles: `coding_agent`, `diy_project`, `knowledge_base` (in `styles/`). `auto` inspects transcript/OCR evidence and routes to the strongest style; ambiguous content prints a recommendation with alternatives.

### Two-phase (re-stylable)

Phase 1 — extract once:

```bash
uv run python extract.py "https://youtu.be/KE39P4qBjDk"
```

Phase 2 — distill with any style; re-run with a different style to get a new note over the same artifacts:

```bash
uv run python distill.py KE39P4qBjDk_Title coding_agent
uv run python distill.py KE39P4qBjDk_Title auto
uv run python distill.py KE39P4qBjDk_Title knowledge_base --model claude-sonnet-4-6
```

Project-local Cursor skills in `.cursor/skills/` mirror these workflows:

- `video-distill-router` chooses the workflow from cheap evidence.
- `youtube-coding-agent` turns developer tutorials into agent-executable implementation guidance.
- `youtube-diy-project` turns maker/how-to videos into build instructions.
- `youtube-knowledge-base` turns talks and conceptual videos into reference notes.

### Local files

```bash
uv run python extract.py /path/to/lecture.mp4 --start 60 --end 600 --max-frames 80
```

`--start`/`--end` (seconds) clip a window; absolute timestamps are preserved through the pipeline so citations like `t=05:23` still mean what you'd expect.

### Useful flags

| Flag | Where | Purpose |
|---|---|---|
| `--max-frames N` | `extract.py`, `run.py` | Cap frames extracted from the video |
| `--start`, `--end` | `extract.py`, `run.py` | Clip a sub-range; timestamps stay absolute |
| `--no-frames` | `extract.py` | Transcript-only run |
| `--keep-video` | `extract.py` | Preserve the cached download for inspection |
| `--force` / `--force-ocr` | `extract.py` | Bypass idempotency for the whole pipeline / OCR only |
| `--cookies-from-browser <browser>` | `extract.py`, `run.py` | Use browser cookies for age-gated / bot-detected videos. Forwarded to all `yt-dlp` calls (probe, captions, download). WSL note: use `chrome`/`edge`, not `firefox` (see Troubleshooting). |
| `--model NAME` | `distill.py`, `run.py` | Override the model profile (CLI > `DISTILL_MODEL` env > `models.yaml` default) |
| `--max-vision-frames N` | `distill.py`, `run.py` | Cap frames sent to the LLM (default 16) |
| `--token-budget N` | `distill.py` | Cap by token budget; trims frames to `min(max_vision_frames, budget // est_image_tokens)` |
| `--dry-run-payload` | `distill.py`, `run.py` | Write `payload.json` (image bytes elided) and exit before calling the LLM |

## Output

Each video gets a directory under `Generated_Data/`:

```
Generated_Data/<title>/
├── artifact_manifest.json              # source_id, file integrity, distill run log
├── extract_meta.json                   # transcript/OCR/coverage quality grades
├── <title>_formatted_transcript.txt    # `start_seconds|text` per line
├── <title>_clean_text.txt              # transcript without timestamps
├── <title>_enriched_transcript.md      # transcript + inline OCR/slide/UI blocks
├── ocr.json                            # per-frame OCR + class + cluster
├── selected_frames.json                # which frames went to the LLM and why
├── frames/                             # frame_NNN_t-MM-SS.jpg
├── <title>_<style>.md                  # final note (Obsidian-ready frontmatter)
└── <title>_<style>.distill_result.json # structured form: summary, key_points, code_blocks, citations…
```

The final markdown has [Obsidian-style](https://obsidian.md/) YAML frontmatter with citation counts, quality grades, model profile, and prompt-contract version.

### Citation contract

The model is constrained to cite at least one of these for every technical claim:

- `seg#NNN` — transcript segment
- `frame_NNN_t-MM-SS` (or short form `frame_NNN`) — specific frame
- `cluster_id=cN` — a deduplicated code-frame cluster
- `t=MM:SS` or `t=MM:SS–MM:SS` — bare timestamp

Unresolved citations (referencing a frame or segment that doesn't exist) cause `distill.py` to exit non-zero with a warning banner in the markdown. The full contract is `prompts/distill_contract_v1.md`.

## Models

`models.yaml` defines profiles. Built-in:

| Profile | Provider | Vision | Reasoning |
|---|---|---|---|
| `gemini-3-flash` (default) | OpenRouter (`google/gemini-3-flash-preview`) | yes | yes |
| `gemini-3-pro` | OpenRouter (`google/gemini-3-pro-preview`) | yes | yes |
| `claude-sonnet-4-6` | OpenRouter (`anthropic/claude-sonnet-4.6`) | yes | no |
| `gpt-4o` | OpenRouter (`openai/gpt-4o`) | yes | no |

Add a new profile with one YAML entry — no code changes. Verify it works:

```bash
uv run python models.py doctor --profile gemini-3-pro
```

`doctor` runs real text/image/reasoning probes against the live API and caches the result for an hour. `distill.py` calls it before each run and falls back to text-only mode if the vision probe fails.

## Cleanup

Dry-run by default; `--apply` to actually delete:

```bash
uv run python clean.py --delete-video --older-than 30d
uv run python clean.py --delete-video --delete-frames --older-than 30d --apply
```

OCR (`ocr.json`) is preserved unless explicitly removed — the cheap-to-keep, expensive-to-recompute artifact.

## Tests

```bash
uv run pytest                         # unit + fast integration
uv run pytest -m integration          # only the slow ones (real ffmpeg, real OCR)
bash scripts/dod_check.sh             # full end-to-end gate (spec §9)
```

The DoD script runs the test suite, extracts + distills the committed fixture video, exercises resumability, runs the legacy CLI, and greps the shipped sources for `TODO`/`XXX`.

## Legal & auth

- You are responsible for having the right to access and process whatever media you pass in.
- This tool does **not** bypass DRM, paywalls, or auth. For age-restricted videos use `--cookies-from-browser firefox` (or `chrome`); cookies stay local.
- Downloaded media should not be redistributed unless you have the right to do so.
- `yt-dlp` extractors break — if a download fails because the extractor is stale, run `uv lock --upgrade-package yt-dlp && uv sync`.

## Troubleshooting

**`Sign in to confirm you're not a bot` / HTTP 429 from YouTube.** Pass `--cookies-from-browser <browser>`. The flag is forwarded to every `yt-dlp` invocation in the pipeline (probe, captions, download). On WSL, `firefox` is **not** supported when Firefox is installed on the Windows host — the WSL profile path doesn't exist; use `chrome` or `edge` instead. The first three transcript tiers (`youtube-transcript-api`, `pytube`, `yt-dlp` subtitles) all read YouTube directly and can be IP-blocked independently.

**All four transcript tiers failed.** Set `GROQ_API_KEY` (preferred — fast, free tier) or `OPENAI_API_KEY` to enable the Whisper fallback. When credentials are present and frames aren't disabled (`--no-frames`), `extract.py` will reuse the downloaded video, extract audio with `ffmpeg`, and transcribe via Whisper. Without a key the tool prints a one-line hint and writes a `# transcript_unavailable` placeholder.

**Stale `pytube` HTTP 400.** `pytube` is largely broken upstream against current YouTube; it stays in the chain as a cheap second attempt but is expected to fail. The downstream tiers (`yt-dlp` subs, `whisper`) carry the load.

## Layout

```
extract.py                      Phase 1 orchestrator
distill.py                      Phase 2 orchestrator
run.py                          extract → distill convenience wrapper
clean.py                        storage management
download_transcript.py          legacy entry point; delegates to run.py when a style is given
models.py                       profile resolution + doctor
manifest.py                     artifact_manifest.json read/write + integrity
transcript.py                   4-tier transcript chain (yt-api → pytube → yt-dlp → whisper)
frame_ocr.py                    RapidOCR + 5-class classifier + rapidfuzz dedup
frame_select.py                 style-aware perceptual-hash scene change + anchored even-spacing
enrichment.py                   splice OCR into transcript at frame timestamps
payload.py                      multimodal LLM payload builder
citation.py                     citation token extract + validate
distill_render.py               distill_result.json → Obsidian markdown
video_profile.py                lightweight router profile for auto style selection
models.yaml                     model profile config
prompts/distill_contract_v1.md  the citation contract sent to every LLM call
styles/                         user-editable style guides
.cursor/skills/                 project-local agent workflows for video distillation
vendor/claude_video/            vendored ffmpeg/whisper helpers (see UPSTREAM.md)
```

## Spec

Full design and rationale: `docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`.
