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
