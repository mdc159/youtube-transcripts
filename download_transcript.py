import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi


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


def _parse_srt(srt_content):
    """Parse SRT format to [(timestamp_seconds, text), ...]"""
    entries = []
    blocks = re.split(r'\n\n+', srt_content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue

        # Line 0: sequence number
        # Line 1: timestamp (00:00:00,000 --> 00:00:00,000)
        # Lines 2+: text
        timestamp_line = lines[1]
        text_lines = lines[2:]

        # Parse start timestamp
        match = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', timestamp_line)
        if match:
            hours, minutes, seconds, millis = map(int, match.groups())
            start_seconds = hours * 3600 + minutes * 60 + seconds + millis / 1000
            text = ' '.join(text_lines).strip()
            if text:
                entries.append((start_seconds, text))

    return entries


def _parse_vtt(vtt_content):
    """Parse VTT format to [(timestamp_seconds, text), ...]

    Handles YouTube's auto-generated VTT which has progressively building captions.
    Each entry shows the full sentence so far, so we take only the final/longest
    version of each sentence by keeping entries where the next entry doesn't
    start with the same text.
    """
    raw_entries = []
    lines = vtt_content.split('\n')

    i = 0
    # Skip header
    while i < len(lines) and not re.match(r'^\d{2}:\d{2}', lines[i]):
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        # Look for timestamp line (00:00:00.000 --> 00:00:00.000)
        match = re.match(r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->', line)
        if not match:
            # Also try format without hours: 00:00.000 --> 00:00.000
            match = re.match(r'(\d{2}):(\d{2})\.(\d{3})\s*-->', line)
            if match:
                minutes, seconds, millis = map(int, match.groups())
                start_seconds = minutes * 60 + seconds + millis / 1000
            else:
                i += 1
                continue
        else:
            hours, minutes, seconds, millis = map(int, match.groups())
            start_seconds = hours * 3600 + minutes * 60 + seconds + millis / 1000

        # Collect text lines until empty line or next timestamp
        i += 1
        text_lines = []
        while i < len(lines):
            text_line = lines[i].strip()
            if not text_line or re.match(r'^\d{2}:\d{2}', text_line):
                break
            # Remove VTT styling tags like <c> </c>
            text_line = re.sub(r'<[^>]+>', '', text_line)
            text_lines.append(text_line)
            i += 1

        text = ' '.join(text_lines).strip()
        if text:
            raw_entries.append((start_seconds, text))

    # Deduplicate: YouTube VTT shows progressive text building
    # Keep only entries that are NOT a prefix of the next entry
    entries = []
    for i, (ts, text) in enumerate(raw_entries):
        # Check if this text is a prefix of the next entry
        if i + 1 < len(raw_entries):
            next_text = raw_entries[i + 1][1]
            if next_text.startswith(text):
                # Skip this entry, the next one is more complete
                continue
        entries.append((ts, text))

    return entries


def _fetch_via_transcript_api(video_id):
    """Primary method: youtube-transcript-api"""
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    return [(entry.start, entry.text) for entry in transcript]


def _fetch_via_pytube(video_id):
    """Fallback 1: pytube captions"""
    from pytube import YouTube

    url = f"https://www.youtube.com/watch?v={video_id}"
    yt = YouTube(url)

    # Try to get English captions first, then any available
    caption = None
    if 'en' in yt.captions:
        caption = yt.captions['en']
    elif 'a.en' in yt.captions:  # Auto-generated English
        caption = yt.captions['a.en']
    elif yt.captions:
        # Get the first available caption
        caption = list(yt.captions.values())[0]

    if not caption:
        raise Exception("No captions available via pytube")

    # Get SRT format and parse it
    srt_content = caption.generate_srt_captions()
    return _parse_srt(srt_content)


def _fetch_via_ytdlp(video_id):
    """Fallback 2: yt-dlp subtitle download"""
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "--skip-download",
            "-o", output_template,
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Find the subtitle file
        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith('.vtt')]

        if not vtt_files:
            raise Exception(f"yt-dlp did not produce subtitle file. stderr: {result.stderr}")

        vtt_path = os.path.join(tmpdir, vtt_files[0])
        with open(vtt_path, 'r', encoding='utf-8') as f:
            vtt_content = f.read()

        return _parse_vtt(vtt_content)


def fetch_transcript_with_fallbacks(video_id):
    """Try each method in sequence until one succeeds."""
    methods = [
        ("youtube-transcript-api", _fetch_via_transcript_api),
        ("pytube", _fetch_via_pytube),
        ("yt-dlp", _fetch_via_ytdlp),
    ]

    errors = []
    for name, method in methods:
        try:
            result = method(video_id)
            print(f"Success with {name}")
            return result
        except Exception as e:
            print(f"{name} failed: {e}")
            errors.append((name, str(e)))
            continue

    print("All transcript methods failed:")
    for name, error in errors:
        print(f"  - {name}: {error}")
    return None


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
        print("Usage: python download_transcript.py <youtube-url-or-id>")
        print("Examples:")
        print("  python download_transcript.py KE39P4qBjDk")
        print("  python download_transcript.py https://youtu.be/KE39P4qBjDk")
        print("  python download_transcript.py 'https://www.youtube.com/watch?v=KE39P4qBjDk'")
        sys.exit(1)

    video_id = extract_video_id(sys.argv[1])
    print(f"Video ID: {video_id}")

    project_root = os.path.dirname(os.path.abspath(__file__))

    # 1. Get Title and Create Directory
    title = get_safe_title(video_id)
    output_dir = os.path.join(project_root, title)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    else:
        print(f"Directory already exists: {output_dir}")

    # 2. Download Transcript
    print(f"Processing: {title}...")
    transcript = download_transcript(video_id, output_dir, title=title)

    if transcript:
        print(f"Successfully saved files to: {output_dir}")
    else:
        print("Failed to process transcript.")
        sys.exit(1)
