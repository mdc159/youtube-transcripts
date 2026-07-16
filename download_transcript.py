import os
import re
import subprocess
import sys
from urllib.parse import urlparse, parse_qs

from yt_distill.stages.transcript import fetch_transcript
from yt_distill.pipeline import run


def extract_video_id(url_or_id):
    """Extract video ID from YouTube URL or return as-is if already an ID."""
    # If it looks like a plain video ID (11 characters, alphanumeric with - and _)
    if re.match(r'^[\w-]{11}$', url_or_id):
        return url_or_id

    # Try parsing as URL
    parsed = urlparse(url_or_id)

    # Handle youtu.be/VIDEO_ID
    if parsed.netloc in ('youtu.be', 'www.youtu.be'):
        return parsed.path.lstrip('/')

    # Handle youtube.com/watch?v=VIDEO_ID
    if parsed.netloc in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            query_params = parse_qs(parsed.query)
            if 'v' in query_params:
                return query_params['v'][0]
        # Handle youtube.com/v/VIDEO_ID or youtube.com/embed/VIDEO_ID
        if parsed.path.startswith(('/v/', '/embed/')):
            return parsed.path.split('/')[2]

    # If nothing matched, return as-is (let the API handle validation)
    return url_or_id


def get_safe_title(video_id):
    try:
        # Use yt-dlp to get the title
        cmd = [
            "yt-dlp",
            "--get-title",
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        title = result.stdout.strip()

        # Remove characters that aren't alphanumeric, spaces, or hyphens
        safe_title = re.sub(r'[^\w\s-]', '', title).strip()
        # Replace spaces and hyphens with underscores
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        return safe_title
    except Exception as e:
        print(f"Warning: Could not fetch title for {video_id} using yt-dlp: {e}")
        return video_id


def fetch_transcript_with_fallbacks(video_id):
    """Backward-compat shim. Returns a list of (start, text) tuples or None.

    Whisper is intentionally NOT enabled here — legacy callers don't pass audio.
    """
    res = fetch_transcript(video_id, allow_whisper=False)
    if res is None:
        return None
    print(f"Success with {res.source}")
    return res.entries


def _extract_unique_text(entries):
    """Extract unique text from entries, removing overlapping portions.

    YouTube VTT entries often overlap: each entry's beginning matches
    the previous entry's ending. For example:
      Entry 1: "Welcome back. This video will be a step-by-step guide"
      Entry 2: "step-by-step guide for developers who want to"

    This extracts only the new portions by finding where each entry
    diverges from what we've already captured.
    """
    if not entries:
        return ""

    # Start with the first entry
    result_text = entries[0][1].strip()

    for i in range(1, len(entries)):
        current_text = entries[i][1].strip()

        # Find the longest suffix of result_text that is a prefix of current_text
        overlap_len = 0
        # Check progressively longer potential overlaps
        for j in range(1, min(len(result_text), len(current_text)) + 1):
            if result_text[-j:] == current_text[:j]:
                overlap_len = j

        # Add only the non-overlapping part
        if overlap_len > 0:
            new_part = current_text[overlap_len:].strip()
            if new_part:
                result_text += " " + new_part
        else:
            # No overlap found, add the whole thing
            result_text += " " + current_text

    return result_text


def _format_as_paragraphs(text):
    """Format text with line breaks after sentences for readability.

    Adds newlines after sentence-ending punctuation (.!?) followed by a space.
    Groups roughly 2-3 sentences per paragraph for natural reading.
    """
    # Split on sentence boundaries (. ! ?) followed by space
    sentences = re.split(r'([.!?])\s+', text)

    # Rejoin sentences with their punctuation
    full_sentences = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and sentences[i + 1] in '.!?':
            full_sentences.append(sentences[i] + sentences[i + 1])
            i += 2
        else:
            if sentences[i].strip():
                full_sentences.append(sentences[i])
            i += 1

    # Group into paragraphs (3 sentences each)
    paragraphs = []
    for i in range(0, len(full_sentences), 3):
        paragraph = ' '.join(full_sentences[i:i + 3])
        paragraphs.append(paragraph)

    return '\n\n'.join(paragraphs)


def download_transcript(video_id, output_dir, title=None):
    """Download transcript using fallback chain and save to files.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save files
        title: Optional title for filenames (defaults to video_id)
    """
    entries = fetch_transcript_with_fallbacks(video_id)

    if not entries:
        print(f"Error: Could not download transcript for {video_id}")
        return None

    # Use title for filenames, fallback to video_id
    file_prefix = title if title else video_id

    # Save raw transcript (start|text)
    raw_path = os.path.join(output_dir, f"{file_prefix}_formatted_transcript.txt")
    with open(raw_path, "w") as f:
        for start, text in entries:
            f.write(f"{start}|{text}\n")

    # Save clean text - extract unique portions and format as paragraphs
    clean_path = os.path.join(output_dir, f"{file_prefix}_clean_text.txt")
    with open(clean_path, "w") as f:
        unique_text = _extract_unique_text(entries)
        formatted_text = _format_as_paragraphs(unique_text)
        f.write(formatted_text)

    return entries


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_transcript.py <youtube-url-or-id> [style]")
        print("  If style is provided, transcript is saved under Generated_Data and transformed with that style.")
        print("Examples:")
        print("  python download_transcript.py KE39P4qBjDk")
        print("  python download_transcript.py 'https://www.youtube.com/watch?v=KE39P4qBjDk' coding_agent")
        sys.exit(1)

    video_id = extract_video_id(sys.argv[1])
    style = sys.argv[2] if len(sys.argv) >= 3 else None
    print(f"Video ID: {video_id}")
    if style:
        print(f"Style: {style}")

    project_root = os.path.dirname(os.path.abspath(__file__))
    output_base = os.path.join(project_root, "Generated_Data")

    if style:
        # Delegate to run.py (extract → distill) for the new pipeline
        print(f"[download_transcript] delegating to run.py for style={style!r}")
        sys.exit(run.main([sys.argv[1], style]))

    # 1. Get Title and Create Directory (always under Generated_Data)
    title = get_safe_title(video_id)
    output_dir = os.path.join(output_base, title)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created directory: {output_dir}")
    else:
        print(f"Directory already exists: {output_dir}")

    # 2. Download Transcript
    print(f"Processing: {title}...")
    transcript = download_transcript(video_id, output_dir, title=title)

    if not transcript:
        print("Failed to process transcript.")
        sys.exit(1)

    print(f"Successfully saved files to: {output_dir}")

    # 3. If style provided, run transform
    if style:
        style_file = os.path.join(project_root, "styles", f"{style}.md")
        if not os.path.isfile(style_file):
            print(f"Warning: Style guide not found: {style_file}")
            print("Skipping transform. Available styles:")
            styles_dir = os.path.join(project_root, "styles")
            if os.path.isdir(styles_dir):
                for f in sorted(os.listdir(styles_dir)):
                    if f.endswith(".md"):
                        print(f"  {f[:-3]}")
        else:
            transform_script = os.path.join(project_root, "transform_transcript.sh")
            if os.path.isfile(transform_script):
                result = subprocess.run(
                    [transform_script, output_dir, style],
                    cwd=project_root,
                )
                if result.returncode != 0:
                    sys.exit(result.returncode)
            else:
                print(f"Warning: transform_transcript.sh not found at {transform_script}")
