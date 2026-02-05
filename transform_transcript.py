#!/usr/bin/env python3
"""Transform a transcript using a style guide via OpenRouter (openrouter/free).

API key: OPENROUTER_API_KEY from environment, or from .env in project root.
Usage: python transform_transcript.py <video_dir> <style_name>
"""

import os
import sys
from datetime import date
from pathlib import Path

# Load .env before reading env vars (project root = parent of this script's dir)
try:
    from dotenv import load_dotenv
    script_dir = Path(__file__).resolve().parent
    load_dotenv(script_dir / ".env")
except ImportError:
    pass

import requests


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"


def get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or not key.strip():
        return None
    return key.strip()


def find_clean_text(video_dir: Path) -> Path | None:
    for f in video_dir.iterdir():
        if f.is_file() and f.name.endswith("_clean_text.txt"):
            return f
    return None


def transform_with_openrouter(style_content: str, transcript_content: str, api_key: str) -> str:
    user_content = (
        f"{style_content}\n\n---\n\n# Transcript to Transform\n\n{transcript_content}\n\n"
        "Transform the above transcript according to the style guide. "
        "Output ONLY the transformed document, no commentary or meta-discussion."
    )
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "reasoning": {"enabled": True},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    message = data["choices"][0]["message"]
    return (message.get("content") or "").strip()


def main() -> int:
    if len(sys.argv) < 3:
        script_dir = Path(__file__).resolve().parent
        styles_dir = script_dir / "styles"
        print("Usage: python transform_transcript.py <video_dir> <style_name>", file=sys.stderr)
        if styles_dir.is_dir():
            print("\nAvailable styles:", file=sys.stderr)
            for f in sorted(styles_dir.glob("*.md")):
                print(f"  {f.stem}", file=sys.stderr)
        return 1

    video_dir = Path(sys.argv[1]).resolve()
    style_name = sys.argv[2]
    script_dir = Path(__file__).resolve().parent
    style_file = script_dir / "styles" / f"{style_name}.md"
    output_base = script_dir / "Generated_Data"

    if not video_dir.is_dir():
        print(f"Error: Directory not found: {video_dir}", file=sys.stderr)
        return 1
    if not style_file.is_file():
        print(f"Error: Style guide not found: {style_file}", file=sys.stderr)
        if (script_dir / "styles").is_dir():
            print("Available styles:", file=sys.stderr)
            for f in sorted((script_dir / "styles").glob("*.md")):
                print(f"  {f.stem}", file=sys.stderr)
        return 1

    clean_text_path = find_clean_text(video_dir)
    if not clean_text_path:
        print(f"Error: No *_clean_text.txt found in {video_dir}", file=sys.stderr)
        return 1

    api_key = get_api_key()
    if not api_key:
        print(
            "Error: OPENROUTER_API_KEY not set. Set it in the environment or in .env.",
            file=sys.stderr,
        )
        return 1

    title = clean_text_path.stem.replace("_clean_text", "")
    video_dir_name = video_dir.name
    output_dir = output_base / video_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{title}_{style_name}.md"
    today = date.today().isoformat()

    style_content = style_file.read_text(encoding="utf-8")
    transcript_content = clean_text_path.read_text(encoding="utf-8")

    print("Transforming transcript...")
    print(f"  Input: {clean_text_path}")
    print(f"  Style: {style_name}")
    print(f"  Output: {output_file}")

    try:
        body = transform_with_openrouter(style_content, transcript_content, api_key)
    except requests.RequestException as e:
        print(f"Error: OpenRouter request failed: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None and hasattr(e.response, "text"):
            print(e.response.text[:500], file=sys.stderr)
        return 1

    front_matter = f"""---
type: tutorial
category: development
domain:
  - youtube-transcript
  - {style_name}
source: youtube-transcript-transform
created: {today}
status: inbox-triage
tags:
  - tutorial
  - {style_name}
  - transformed-transcript
summary: Transformed YouTube transcript using {style_name} style guide.
enriched_at: ""
---

"""

    output_file.write_text(front_matter + body, encoding="utf-8")
    print(f"\nCreated: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
