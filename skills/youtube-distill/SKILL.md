---
name: youtube-distill
description: "Use when a YouTube URL or local video needs citation-grounded transcription, frame OCR, and multimodal distillation via the yt-distill CLI — evidence artifacts, style routing, lesson bundles, multi-video family synthesis. Not for quick transcript-only summaries (use youtube-content for those)."
version: 0.1.0
author: Mike + Hermes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [youtube, transcription, ocr, distillation, citations, video]
    related_skills: [youtube-content]
---

# YouTube Distill

Drive the `yt-distill` CLI (repo: `youtube-transcripts`) to turn a YouTube URL or local video into citation-grounded, multimodal artifacts: transcript + OCR'd frames + style-routed LLM notes, every technical claim citing a transcript segment, frame, code cluster, or timestamp.

The CLI is the engine. This skill is the operating contract — never re-implement the pipeline in skill scripts.

## When to Use

- Transcribe/distill a video when citations, frames, or downstream reuse matter.
- Re-style an already-extracted video without re-downloading.
- Turn a long tutorial into a self-sufficient `claude_skill` bundle.
- Synthesize several videos + local assets into per-topic docs → load `references/family-synthesis.md`.

**Don't use for:** quick transcript/summary requests with no evidence needs — the `youtube-content` skill is lighter and cheaper.

## Repo Bootstrap

1. Locate the checkout: try `D:/Projects/youtube-transcripts`, then search for `yt_distill/cli.py`. If absent, `git clone https://github.com/mdc159/youtube-transcripts.git`.
2. From the repo root: verify `uv`, `ffmpeg -version`, `ffprobe`. Run `uv sync`.
3. Keys: default model profile reads `OPENROUTER_API_KEY`; Whisper fallback reads `GROQ_API_KEY` (preferred) or `OPENAI_API_KEY`. The CLI loads repo-root `.env` itself — copy values from machine/User env or the Hermes `.env` if the shell doesn't have them (never print them).
4. **All commands run from the repo root** via `uv run yt-distill ...`. Artifacts land in `Generated_Data/<title>/`.

## Command Routing

| Need | Command |
|---|---|
| Artifacts only (transcript/frames/OCR) | `uv run yt-distill extract "<url-or-path>"` |
| One video, one note | `uv run yt-distill distill <title-dir> <style>` or `run "<url>" <style>` |
| Unsure which style | `distill <title-dir> auto` (`--dry-run-payload` to preview routing free) |
| Human follow-along guide | style `human_tutorial` (explicit only) |
| Self-sufficient lesson bundle | `extract → refs → distill <dir> claude_skill → review <dir>` |
| Check a model profile works | `uv run yt-distill doctor --profile <name>` |
| Several videos + local assets → per-topic docs | `references/family-synthesis.md` |

Styles: `coding_agent`, `diy_project`, `knowledge_base`, `human_tutorial`, `claude_skill`. `auto` never routes to the last two.

## Run Workflow (per video)

1. **Extract**: `uv run yt-distill extract "<url>"`. Long (download + frames + OCR) — run as a background job with a completion marker, don't block on it.
   - YouTube bot-check/429 → retry with `--cookies-from-browser chrome` (or `edge`; never `firefox` from WSL).
   - Done when: `Generated_Data/<title>/` has `artifact_manifest.json`, `extract_meta.json`, `ocr.json`, `frames/`, and NO `# transcript_unavailable` placeholder.
2. **Distill**: `uv run yt-distill distill <title-dir> <style-or-auto>`.
   - Done when: `<title>_<style>.md` + `.distill_result.json` exist and the command exits 0. Unresolved citations = non-zero exit = failure — inspect, don't ship.
3. **Verify** the artifact set (see checklist), then re-style or synthesize from the same artifacts — extract is idempotent.

## Verification Checklist

- [ ] `extract_meta.json` quality grades acceptable; transcript tier recorded
- [ ] `ocr.json` non-empty for screen-heavy videos; frames present
- [ ] Distill exit code 0; markdown frontmatter has citation counts, model profile, contract version
- [ ] For `claude_skill`: `skills/<slug>/` bundle exists and `review` ran (or was explicitly skipped)

## Common Pitfalls

1. **Empty transcript, exit 0.** Tiers 1–3 blocked and no Whisper key → placeholder file. Check for `# transcript_unavailable` before calling a run done.
2. **`pytube` 400s are expected noise** — tiers 3–4 carry the load.
3. **Re-running extract is cheap** (manifest skips intact work). `--force` only when outputs are actually stale; `--force-ocr` re-runs only OCR.
4. **Running from the wrong cwd.** `Generated_Data/` is created under cwd in some paths — always `cd` to repo root first.
5. **Stale yt-dlp** on download failures: `uv lock --upgrade-package yt-dlp && uv sync`.
