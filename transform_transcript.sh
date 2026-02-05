#!/bin/bash
# Transform a transcript using a style guide via OpenRouter (openrouter/free)
# Usage: ./transform_transcript.sh <video_dir> <style_name>
# Requires OPENROUTER_API_KEY in environment or .env

set -e

VIDEO_DIR="$1"
STYLE="$2"
SCRIPT_DIR="$(dirname "$0")"

# Validate arguments
if [[ -z "$VIDEO_DIR" || -z "$STYLE" ]]; then
    echo "Usage: ./transform_transcript.sh <video_dir> <style_name>"
    echo ""
    echo "Available styles:"
    ls -1 "${SCRIPT_DIR}/styles/" 2>/dev/null | sed 's/\.md$//' | sed 's/^/  /'
    exit 1
fi

# Validate video directory exists
if [[ ! -d "$VIDEO_DIR" ]]; then
    echo "Error: Directory not found: $VIDEO_DIR"
    exit 1
fi

# Validate style guide exists
STYLE_FILE="${SCRIPT_DIR}/styles/${STYLE}.md"
if [[ ! -f "$STYLE_FILE" ]]; then
    echo "Error: Style guide not found: $STYLE_FILE"
    echo ""
    echo "Available styles:"
    ls -1 "${SCRIPT_DIR}/styles/" 2>/dev/null | sed 's/\.md$//' | sed 's/^/  /'
    exit 1
fi

# Validate clean text file exists
if [[ -z "$(find "$VIDEO_DIR" -name "*_clean_text.txt" | head -1)" ]]; then
    echo "Error: No *_clean_text.txt file found in $VIDEO_DIR"
    exit 1
fi

# Run Python transform (OpenRouter)
TRANSFORM_SCRIPT="${SCRIPT_DIR}/transform_transcript.py"
if [[ ! -f "$TRANSFORM_SCRIPT" ]]; then
    echo "Error: transform_transcript.py not found at $TRANSFORM_SCRIPT"
    exit 1
fi
uv run python "$TRANSFORM_SCRIPT" "$VIDEO_DIR" "$STYLE"
exit $?
