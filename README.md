# YouTube Transcripts

Download YouTube video transcripts with timestamps. Output is saved under `Generated_Data/` in directories named after video titles.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
uv run python download_transcript.py <youtube-url-or-id> [style]
```

- **URL or ID** (required): Full URL or 11-character video ID (e.g. `https://www.youtube.com/watch?v=CL0vkl8Sxvs` or `CL0vkl8Sxvs`).
- **style** (optional): If provided, after downloading the transcript is transformed using that style guide (from `styles/<style>.md`) via OpenRouter (`openrouter/free`). Without it, only the transcript is downloaded.

All output is written under `Generated_Data/<video_title>/`.

**Transform step (when using a style):** The API key is read from the `OPENROUTER_API_KEY` environment variable or from a `.env` file in the project root. Create `.env` with `OPENROUTER_API_KEY=your_key` or export it in your shell.

The script creates (in that directory):

| File | Description |
|------|-------------|
| `formatted_transcript.txt` | Timestamped format: `<seconds>\|<text>` per line |
| `clean_text.txt` | Plain text without timestamps |

## Example

For a video titled "I Was Wrong About Best Practices":

```
Generated_Data/I_Was_Wrong_About_Best_Practices/
├── I_Was_Wrong_About_Best_Practices_formatted_transcript.txt
├── I_Was_Wrong_About_Best_Practices_clean_text.txt
└── (if style given) I_Was_Wrong_About_Best_Practices_<style>.md
```

**formatted_transcript.txt:**
```
0.0|hey everyone welcome back
3.5|today we're going to talk about
```

**clean_text.txt:**
```
hey everyone welcome back today we're going to talk about...
```

## Extracting Video ID

From URL `https://www.youtube.com/watch?v=CL0vkl8Sxvs`, the video ID is `CL0vkl8Sxvs`.

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
