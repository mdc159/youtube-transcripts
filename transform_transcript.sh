#!/bin/bash
# Transform a transcript using a style guide via Claude Code
# Usage: ./transform_transcript.sh <video_dir> <style_name>

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

# Find the clean text file
CLEAN_TEXT=$(find "$VIDEO_DIR" -name "*_clean_text.txt" | head -1)

if [[ -z "$CLEAN_TEXT" ]]; then
    echo "Error: No *_clean_text.txt file found in $VIDEO_DIR"
    exit 1
fi

# Extract title from filename
TITLE=$(basename "$CLEAN_TEXT" _clean_text.txt)
OUTPUT="${VIDEO_DIR}/${TITLE}_${STYLE}.md"

echo "Transforming transcript..."
echo "  Input: $CLEAN_TEXT"
echo "  Style: $STYLE"
echo "  Output: $OUTPUT"

# Combine style guide with transcript and pipe to Claude
# (--system-prompt doesn't work well with --print, so we concatenate instead)
{
    cat "$STYLE_FILE"
    echo ""
    echo "---"
    echo ""
    echo "# Transcript to Transform"
    echo ""
    cat "$CLEAN_TEXT"
} | claude --print "Transform the above transcript according to the style guide. Output ONLY the transformed document, no commentary or meta-discussion." \
    > "$OUTPUT"

echo ""
echo "Created: $OUTPUT"
