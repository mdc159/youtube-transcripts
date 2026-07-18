# YouTube Transcripts

Turn a YouTube URL or local video into a citation-grounded, multimodal artifact for an agent workflow. The pipeline pulls a transcript, extracts and OCRs visual evidence, classifies what's on screen (code / slide / UI / diagram), optionally follows linked sources (repos pinned to a commit SHA, docs), routes the content to the best skill-style workflow, then sends an enriched payload to a vision-capable LLM where every claim cites a transcript segment, frame, cluster, timestamp, or pinned repository line range.

## How it works

Two phases, written so you can re-route or re-style without re-downloading:

```
yt-distill extract  ─►  Generated_Data/<title>/  ─►  yt-distill distill
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

`yt-distill extract` is idempotent — re-running skips work whose outputs are still intact. `yt-distill distill` can use an explicit style or `auto`, which builds a lightweight video profile from transcript and OCR signals, picks `coding_agent`, `diy_project`, or `knowledge_base`, runs style-aware frame selection, builds a multimodal payload, validates the model can actually do what its profile claims (`doctor`), then calls the LLM and validates every citation in the response. `yt-distill run` chains both for one-shot use.

## Install

Requires Python 3.11–3.12 (the lower bound is forced by `rapidocr-onnxruntime` wheels), [uv](https://docs.astral.sh/uv/), and `ffmpeg`/`ffprobe` on PATH.

```bash
uv sync
```

Set an API key for whichever model profile you want to use. The default profile (`gemini-3.5-flash`) reads `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY=sk-or-...
# or put it in .env
```

## Usage

### One-shot

```bash
uv run yt-distill run "https://www.youtube.com/watch?v=KE39P4qBjDk" coding_agent
uv run yt-distill run "https://www.youtube.com/watch?v=KE39P4qBjDk" auto
```

Downloads, extracts frames + OCR, and distills with either an explicit style or the router. Available styles: `coding_agent`, `diy_project`, `knowledge_base`, `human_tutorial`, `claude_skill` (in `styles/`). `auto` inspects transcript/OCR evidence and routes to the strongest style; ambiguous content prints a recommendation with alternatives. `human_tutorial` and `claude_skill` are explicit-only — `auto` never routes to them.

### Two-phase (re-stylable)

Phase 1 — extract once:

```bash
uv run yt-distill extract "https://youtu.be/KE39P4qBjDk"
```

Phase 2 — distill with any style; re-run with a different style to get a new note over the same artifacts:

```bash
uv run yt-distill distill KE39P4qBjDk_Title coding_agent
uv run yt-distill distill KE39P4qBjDk_Title auto
uv run yt-distill distill KE39P4qBjDk_Title knowledge_base --model claude-sonnet-4-6
```

Project-local Cursor skills in `.cursor/skills/` mirror these workflows:

- `video-distill-router` chooses the workflow from cheap evidence.
- `youtube-coding-agent` turns developer tutorials into agent-executable implementation guidance.
- `youtube-diy-project` turns maker/how-to videos into build instructions.
- `youtube-knowledge-base` turns talks and conceptual videos into reference notes.
- `youtube-human-tutorial` turns tutorials into conversational follow-along guides for a human reader (explicit style only; `auto` never routes here).
- `youtube-claude-skill` turns long-form tutorials into self-sufficient skill packages for a consuming agent (explicit style only; `auto` never routes here).

### Lesson liberation (skill packages)

Two additional phases turn a long-form tutorial into a self-sufficient skill package another agent can follow without the source:

```bash
uv run yt-distill refs KE39P4qBjDk_Title                 # harvest links: clone repos @SHA, fetch docs
uv run yt-distill distill KE39P4qBjDk_Title claude_skill # emits skills/<slug>/ bundle (+reconciliation)
uv run yt-distill review KE39P4qBjDk_Title               # fresh-context reviewer → gaps → re-synthesize
```

`yt-distill refs` harvests URLs from the description, pinned/top comments, transcript, and OCR (resolving link shorteners), classifies them (`github_repo | docs | asset_download | other`), shallow-clones repos pinned to a commit SHA, and snapshots key files (budgets: `--max-repo-mb`, `--max-fetches`). When pinned repo snapshots exist, `yt-distill distill` runs a reconciliation pass — repo code is authoritative for exact syntax, the transcript for intent and ordering, OCR clusters bridge the two — and conflicts are flagged in the note, never silently resolved. The `claude_skill` style then emits `skills/<slug>/` containing `SKILL.md` (build manifest, imperative lessons, techniques, gotchas, open gaps; every step `status: distilled`), `assets/` (cited frames), `reference/` (repo pointers + snapshots + docs), and `provenance.json`.

`yt-distill review` is the quality gate: a fresh-context reviewer sees only the bundle, dry-runs every step, and reports gaps wherever it would be guessing; gaps escalate deterministically (targeted `ffmpeg` frame grabs at flagged timestamps, snapshot repo pulls, transcript re-reads) and a re-synthesis closes them. After `--max-iterations` (default 3) the bundle ships marked `incomplete` with the residual gap list in provenance. Per-phase models: `--review-model` / `--synth-model`.

An Archon workflow wrapping the full chain lives at `.archon/workflows/lesson-liberation.yaml`.

### Local files

```bash
uv run yt-distill extract /path/to/lecture.mp4 --start 60 --end 600 --max-frames 80
```

`--start`/`--end` (seconds) clip a window; absolute timestamps are preserved through the pipeline so citations like `t=05:23` still mean what you'd expect.

### Useful flags

| Flag | Where | Purpose |
|---|---|---|
| `--max-frames N` | `extract`, `run` | Cap frames extracted from the video |
| `--start`, `--end` | `extract`, `run` | Clip a sub-range; timestamps stay absolute |
| `--out-dir PATH` | `extract` | Override the `Generated_Data` root directory |
| `--no-frames` | `extract` | Transcript-only run |
| `--keep-video` | `extract` | Preserve the cached download for inspection |
| `--force` / `--force-ocr` | `extract` | Bypass idempotency for the whole pipeline / OCR only |
| `--cookies-from-browser <browser>` | `extract`, `run` | Use browser cookies for age-gated / bot-detected videos. Forwarded to all `yt-dlp` calls (probe, captions, download). WSL note: use `chrome`/`edge`, not `firefox` (see Troubleshooting). |
| `--model NAME` | `distill`, `run` | Override the model profile (CLI > `DISTILL_MODEL` env > `models.yaml` default) |
| `--max-vision-frames N` | `distill`, `run` | Cap frames sent to the LLM (default 16) |
| `--token-budget N` | `distill` | Cap by token budget; trims frames to `min(max_vision_frames, budget // est_image_tokens)` |
| `--enrich`, `--no-enrich` | `distill`, `run` | Force/skip the post-processor (inline frames, Mermaid, tables). Default: ON for `human_tutorial`, OFF otherwise. |
| `--audience-note TEXT` | `distill`, `run` | Prepend a free-form audience profile to the style guide for tone/depth tuning |
| `--dry-run-payload` | `distill`, `run` | Write `payload.json` (image bytes elided) and exit before calling the LLM |

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
├── references.json                     # harvested links + provenance (yt-distill refs)
├── refs/                               # repo snapshots @SHA, fetched docs, source_meta.json
├── reconciliation.json                 # transcript↔OCR↔repo alignments + flagged conflicts
├── frames_targeted/                    # review-loop targeted grabs (tgrab_SSSSSS.jpg)
├── skills/<slug>/                      # claude_skill bundle: SKILL.md, assets/, reference/, provenance.json
├── <title>_<style>.md                  # final note (Obsidian-ready frontmatter)
└── <title>_<style>.distill_result.json # structured form: summary, key_points, code_blocks, citations…
```

(`references.json`/`refs/` appear after running `yt-distill refs`; `reconciliation.json` only when pinned repo snapshots exist; `frames_targeted/` and `skills/` only on the `claude_skill` path.)

The final markdown has [Obsidian-style](https://obsidian.md/) YAML frontmatter with citation counts, quality grades, model profile, and prompt-contract version.

### Citation contract

The model is constrained to cite at least one of these for every technical claim:

- `seg#NNN` — transcript segment
- `frame_NNN_t-MM-SS` (or short form `frame_NNN`) — specific frame
- `cluster_id=cN` — a deduplicated code-frame cluster
- `t=MM:SS` (also `H:MM:SS` / `MMM:SS` for videos past 99 minutes), optionally as a `–` range — bare timestamp
- `repo:path/to/file#L10-L40@SHA` — pinned repository line range (contract v2 only)

Unresolved citations (referencing a frame, segment, or repo file that doesn't exist) cause `yt-distill distill` to exit non-zero with a warning banner in the markdown. The base contract is `prompts/distill_contract_v1.md`; when reference following has pinned repo snapshots, `yt-distill distill` automatically upgrades to `prompts/distill_contract_v2.md`, which adds the repo citation kind and conflict-flagging rules.

## Models

`models.yaml` defines profiles. Built-in:

| Profile | Provider | Vision | Reasoning |
|---|---|---|---|
| `gemini-3.5-flash` (default) | OpenRouter (`google/gemini-3.5-flash`) | yes | yes |
| `gemini-3.5-flash-high` | OpenRouter (`google/gemini-3.5-flash`, reasoning_effort=high) | yes | yes |
| `kimi-k3` | OpenRouter (`moonshotai/kimi-k3`) | yes | yes |
| `gemini-3-flash` | OpenRouter (`google/gemini-3-flash-preview`) | yes | yes |
| `gemini-3-pro` | OpenRouter (`google/gemini-3-pro-preview`) | yes | yes |
| `claude-sonnet-4-6` | OpenRouter (`anthropic/claude-sonnet-4.6`) | yes | no |
| `gpt-4o` | OpenRouter (`openai/gpt-4o`) | yes | no |

Add a new profile with one YAML entry — no code changes. Verify it works:

```bash
uv run yt-distill doctor --profile gemini-3-pro
```

`doctor` runs real text/image/reasoning probes against the live API and caches the result for an hour. `yt-distill distill` calls it before each run and falls back to text-only mode if the vision probe fails.

## Cleanup

Dry-run by default; `--apply` to actually delete:

```bash
uv run yt-distill clean --delete-video --older-than 30d
uv run yt-distill clean --delete-video --delete-frames --older-than 30d --apply
```

OCR (`ocr.json`) is preserved unless explicitly removed — the cheap-to-keep, expensive-to-recompute artifact.

## Tests

```bash
uv run pytest                         # unit + fast integration
uv run pytest -m integration          # only the slow ones (real ffmpeg, real OCR)
bash scripts/dod_check.sh             # full end-to-end gate (spec §9)
```

The DoD script runs the test suite, extracts + distills the committed fixture video, exercises resumability, and greps the shipped sources for `TODO`/`XXX`.

## Legal & auth

- You are responsible for having the right to access and process whatever media you pass in.
- This tool does **not** bypass DRM, paywalls, or auth. For age-restricted videos use `--cookies-from-browser firefox` (or `chrome`); cookies stay local.
- Downloaded media should not be redistributed unless you have the right to do so.
- `yt-dlp` extractors break — if a download fails because the extractor is stale, run `uv lock --upgrade-package yt-dlp && uv sync`.

## Troubleshooting

**`Sign in to confirm you're not a bot` / HTTP 429 from YouTube.** Pass `--cookies-from-browser <browser>`. The flag is forwarded to every `yt-dlp` invocation in the pipeline (probe, captions, download). On WSL, `firefox` is **not** supported when Firefox is installed on the Windows host — the WSL profile path doesn't exist; use `chrome` or `edge` instead. The first three transcript tiers (`youtube-transcript-api`, `pytube`, `yt-dlp` subtitles) all read YouTube directly and can be IP-blocked independently.

**All four transcript tiers failed.** Set `GROQ_API_KEY` (preferred — fast, free tier) or `OPENAI_API_KEY` to enable the Whisper fallback. When credentials are present and frames aren't disabled (`--no-frames`), `yt-distill extract` will reuse the downloaded video, extract audio with `ffmpeg`, and transcribe via Whisper. Without a key the tool prints a one-line hint and writes a `# transcript_unavailable` placeholder.

**Stale `pytube` HTTP 400.** `pytube` is largely broken upstream against current YouTube; it stays in the chain as a cheap second attempt but is expected to fail. The downstream tiers (`yt-dlp` subs, `whisper`) carry the load.

## Layout

```
src/yt_distill/cli.py                    `yt-distill` command dispatcher
src/yt_distill/pipeline/extract.py       Phase 1 orchestrator
src/yt_distill/stages/references.py      Phase 1.5: harvest links → classify → snapshot repos @SHA / fetch docs
src/yt_distill/pipeline/distill.py       Phase 2 orchestrator (+reconciliation, +claude_skill bundle emission)
src/yt_distill/pipeline/review.py        Phase 3: fresh-context downstream review → escalate → re-synthesize
src/yt_distill/pipeline/run.py           extract → distill convenience wrapper
src/yt_distill/stages/visual.py          standalone visual-evidence enrichment
src/yt_distill/clean.py                  storage management
src/yt_distill/core/models.py            profile resolution + doctor
src/yt_distill/core/manifest.py          artifact_manifest.json read/write + integrity
src/yt_distill/stages/transcript.py      4-tier transcript chain (yt-api → pytube → yt-dlp → whisper)
src/yt_distill/stages/frame_ocr.py       RapidOCR + 5-class classifier + rapidfuzz dedup
src/yt_distill/stages/frame_select.py    style-aware perceptual-hash scene change + anchored even-spacing
src/yt_distill/stages/registry.py        stage registration and cost-tier ordering
src/yt_distill/core/enrichment.py        splice OCR into transcript at frame timestamps
src/yt_distill/core/payload.py           multimodal LLM payload builder
src/yt_distill/core/citation.py          citation token extract + validate (incl. repo:path#Lx-Ly@SHA)
src/yt_distill/core/reconcile.py         transcript↔OCR↔repo cross-check; conflicts flagged, never resolved
src/yt_distill/output/skill_bundle.py    claude_skill bundle writer (SKILL.md, assets/, reference/, provenance)
src/yt_distill/output/render.py          distill_result.json → Obsidian markdown
src/yt_distill/core/video_profile.py     lightweight router profile for auto style selection
src/yt_distill/core/env_bootstrap.py     per-entry-point .env loading + DNS fallback arming
src/yt_distill/core/dns_fallback.py      DoH fallback resolver for port-53-filtered networks
models.yaml                     model profile config
prompts/distill_contract_v1.md  the citation contract sent to every LLM call
prompts/distill_contract_v2.md  v1 + repo citations & conflict rules (auto-selected with repo evidence)
styles/                         user-editable style guides
.archon/workflows/              Archon workflow wrapping the lesson-liberation chain
.cursor/skills/                 project-local agent workflows for video distillation
vendor/claude_video/            vendored ffmpeg/whisper helpers (see UPSTREAM.md)
```

## Spec

Full design and rationale: `docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`.
