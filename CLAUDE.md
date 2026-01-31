# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube transcript downloader that fetches transcripts using `youtube-transcript-api` and video titles using `yt-dlp`. Downloads are saved to directories named after sanitized video titles.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run the main transcript downloader
uv run python download_transcript.py

# Activate venv manually if needed
source .venv/bin/activate
```

## Architecture

- **download_transcript.py** - Main script with two functions:
  - `get_safe_title(video_id)` - Fetches video title via yt-dlp, sanitizes for filesystem
  - `download_transcript(video_id, output_dir)` - Downloads transcript and saves two formats:
    - `formatted_transcript.txt` - Timestamped format (`start|text`)
    - `clean_text.txt` - Plain text without timestamps

- **main.py** - Placeholder entry point (unused)

## Output Structure

Each downloaded video creates a directory with sanitized title containing:
```
<VideoTitle>/
├── formatted_transcript.txt   # timestamp|text per line
└── clean_text.txt            # concatenated plain text
```

## Dependencies

- `youtube-transcript-api` - Fetches YouTube auto-generated/manual transcripts
- `yt-dlp` - Extracts video metadata (title)
- `pytube` - Available but currently unused
