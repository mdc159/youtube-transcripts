#!/usr/bin/env python3
"""Test multiple LLMs on the same transcript transformation.

Compares output from different OpenRouter models to see quality differences.
Usage: python test_models.py <video_dir> <style_name> [--models model1,model2,...]
"""

import os
import sys
import time
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    script_dir = Path(__file__).resolve().parent
    load_dotenv(script_dir / ".env")
except ImportError:
    pass

from openai import APIError, OpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Default models to test
DEFAULT_MODELS = [
    "openrouter/free",
    "google/gemini-3-flash-preview",
    "google/gemini-3-pro-preview",
    "moonshotai/kimi-k2.5",
    "openai/gpt-5-nano",
]


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


def transform_with_model(
    model: str,
    style_content: str,
    transcript_content: str,
    api_key: str,
) -> tuple[str, float, dict]:
    """Transform transcript with a specific model.
    
    Returns: (content, elapsed_seconds, usage_info)
    """
    user_content = (
        f"{style_content}\n\n---\n\n# Transcript to Transform\n\n{transcript_content}\n\n"
        "Transform the above transcript according to the style guide. "
        "Output ONLY the transformed document, no commentary or meta-discussion."
    )
    
    client = OpenAI(base_url=OPENROUTER_BASE, api_key=api_key)
    
    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_content}],
        extra_body={"reasoning": {"enabled": True}},
    )
    elapsed = time.time() - start
    
    message = response.choices[0].message
    content = (message.content or "").strip()
    
    # Extract usage info if available
    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    
    return content, elapsed, usage


def sanitize_model_name(model: str) -> str:
    """Convert model name to safe filename."""
    return model.replace("/", "_").replace(":", "_").replace(".", "-")


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python test_models.py <video_dir> <style_name> [--models m1,m2,...]")
        print("\nDefault models:", ", ".join(DEFAULT_MODELS))
        return 1
    
    video_dir = Path(sys.argv[1]).resolve()
    style_name = sys.argv[2]
    
    # Parse --models argument
    models = DEFAULT_MODELS.copy()
    for arg in sys.argv[3:]:
        if arg.startswith("--models="):
            models = [m.strip() for m in arg.split("=", 1)[1].split(",")]
        elif arg == "--models" and sys.argv.index(arg) + 1 < len(sys.argv):
            idx = sys.argv.index(arg)
            models = [m.strip() for m in sys.argv[idx + 1].split(",")]
    
    script_dir = Path(__file__).resolve().parent
    style_file = script_dir / "styles" / f"{style_name}.md"
    output_base = script_dir / "Generated_Data"
    
    # Validate inputs
    if not video_dir.is_dir():
        print(f"Error: Directory not found: {video_dir}", file=sys.stderr)
        return 1
    if not style_file.is_file():
        print(f"Error: Style guide not found: {style_file}", file=sys.stderr)
        return 1
    
    clean_text_path = find_clean_text(video_dir)
    if not clean_text_path:
        print(f"Error: No *_clean_text.txt found in {video_dir}", file=sys.stderr)
        return 1
    
    api_key = get_api_key()
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set.", file=sys.stderr)
        return 1
    
    # Setup
    title = clean_text_path.stem.replace("_clean_text", "")
    video_dir_name = video_dir.name
    output_dir = output_base / video_dir_name / "model_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    
    style_content = style_file.read_text(encoding="utf-8")
    transcript_content = clean_text_path.read_text(encoding="utf-8")
    
    print(f"Testing {len(models)} models on: {title}")
    print(f"Style: {style_name}")
    print(f"Output dir: {output_dir}")
    print("-" * 60)
    
    results = []
    
    for model in models:
        print(f"\n[{model}]")
        print("  Requesting...", end=" ", flush=True)
        
        try:
            content, elapsed, usage = transform_with_model(
                model, style_content, transcript_content, api_key
            )
            
            if not content:
                print(f"EMPTY RESPONSE")
                results.append({
                    "model": model,
                    "status": "empty",
                    "elapsed": elapsed,
                })
                continue
            
            # Save output
            safe_model = sanitize_model_name(model)
            output_file = output_dir / f"{title}_{style_name}_{safe_model}.md"
            
            front_matter = f"""---
type: tutorial
category: development
domain:
  - youtube-transcript
  - {style_name}
source: youtube-transcript-transform
model: {model}
created: {today}
status: model-test
tags:
  - model-comparison
  - {style_name}
---

"""
            output_file.write_text(front_matter + content, encoding="utf-8")
            
            # Stats
            lines = len(content.split("\n"))
            chars = len(content)
            
            print(f"OK ({elapsed:.1f}s)")
            print(f"  Output: {lines} lines, {chars} chars")
            if usage:
                print(f"  Tokens: {usage.get('prompt_tokens', '?')} in, {usage.get('completion_tokens', '?')} out")
            print(f"  File: {output_file.name}")
            
            results.append({
                "model": model,
                "status": "ok",
                "elapsed": elapsed,
                "lines": lines,
                "chars": chars,
                "usage": usage,
                "file": output_file.name,
            })
            
        except (APIError, ValueError, Exception) as e:
            print(f"FAILED: {e}")
            results.append({
                "model": model,
                "status": "error",
                "error": str(e),
            })
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Model':<40} {'Status':<8} {'Time':>8} {'Lines':>8}")
    print("-" * 60)
    for r in results:
        status = r["status"]
        elapsed = f"{r.get('elapsed', 0):.1f}s" if "elapsed" in r else "-"
        lines = str(r.get("lines", "-"))
        print(f"{r['model']:<40} {status:<8} {elapsed:>8} {lines:>8}")
    
    # Save summary
    summary_file = output_dir / f"_summary_{style_name}_{today}.md"
    with open(summary_file, "w") as f:
        f.write(f"# Model Comparison: {title}\n\n")
        f.write(f"- **Style**: {style_name}\n")
        f.write(f"- **Date**: {today}\n")
        f.write(f"- **Transcript**: {clean_text_path.name}\n\n")
        f.write("## Results\n\n")
        f.write("| Model | Status | Time | Lines | Chars |\n")
        f.write("|-------|--------|------|-------|-------|\n")
        for r in results:
            model = r["model"]
            status = r["status"]
            elapsed = f"{r.get('elapsed', 0):.1f}s" if "elapsed" in r else "-"
            lines = str(r.get("lines", "-"))
            chars = str(r.get("chars", "-"))
            f.write(f"| {model} | {status} | {elapsed} | {lines} | {chars} |\n")
        f.write(f"\n## Files\n\n")
        for r in results:
            if r.get("file"):
                f.write(f"- `{r['file']}`\n")
    
    print(f"\nSummary saved: {summary_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
