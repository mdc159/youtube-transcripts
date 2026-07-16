#!/usr/bin/env bash
# scripts/dod_check.sh — runs every DoD condition listed in spec §9.
set -euo pipefail

echo "=== DoD: pytest ==="
uv run pytest

echo "=== DoD: extract on test_video.mp4 ==="
TMP=$(mktemp -d)
echo "[dod] TMP=$TMP"
YT_GENERATED_DATA_DIR=$TMP uv run yt-distill extract tests/fixtures/test_video.mp4 --max-frames 6
test -f "$TMP/test_video/artifact_manifest.json"
test -f "$TMP/test_video/ocr.json"
test -d "$TMP/test_video/frames"

echo "=== DoD: distill --dry-run-payload ==="
# We monkey-patch doctor() to bypass the live capability probe; --dry-run-payload
# does not call the LLM, so no API key is needed.
YT_GENERATED_DATA_DIR=$TMP uv run python -c "
import sys
from yt_distill.pipeline import distill
distill.doctor = lambda *a, **k: type('R', (), {'ok': True, 'failure_reason': ''})()
sys.exit(distill.main(['test_video', 'knowledge_base', '--dry-run-payload']))
"
test -f "$TMP/test_video/payload.json"

echo "=== DoD: resumability ==="
YT_GENERATED_DATA_DIR=$TMP uv run yt-distill extract tests/fixtures/test_video.mp4 --max-frames 6
rm -f "$TMP"/test_video/frames/*.jpg | head -1
YT_GENERATED_DATA_DIR=$TMP uv run yt-distill extract tests/fixtures/test_video.mp4 --max-frames 6

echo "=== DoD: no TODO/XXX in shipped source ==="
! grep -rn -E "(TODO|XXX)" --include="*.py" src/yt_distill

echo "=== DoD complete ==="
