# YouTube Transcripts

Download YouTube video transcripts with timestamps. Automatically names output directories after video titles.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

Edit `download_transcript.py` and set the `video_id`:

```python
video_id = "CL0vkl8Sxvs"  # YouTube video ID from URL
```

Run:

```bash
uv run python download_transcript.py
```

The script creates a directory named after the video title containing:

| File | Description |
|------|-------------|
| `formatted_transcript.txt` | Timestamped format: `<seconds>\|<text>` per line |
| `clean_text.txt` | Plain text without timestamps |

## Example

For a video titled "I Was Wrong About Best Practices":

```
I_Was_Wrong_About_Best_Practices/
├── formatted_transcript.txt
└── clean_text.txt
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
