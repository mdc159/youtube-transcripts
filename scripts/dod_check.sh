#!/usr/bin/env bash
# scripts/dod_check.sh — runs every DoD condition listed in spec §9.
set -euo pipefail

echo "=== DoD: pytest ==="
uv run pytest

echo "=== DoD: extract on test_video.mp4 ==="
TMP=$(mktemp -d)
echo "[dod] TMP=$TMP"
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6
test -f "$TMP/test_video/artifact_manifest.json"
test -f "$TMP/test_video/ocr.json"
test -d "$TMP/test_video/frames"

echo "=== DoD: distill --dry-run-payload ==="
# We monkey-patch doctor() to bypass the live capability probe; --dry-run-payload
# does not call the LLM, so no API key is needed.
YT_GENERATED_DATA_DIR=$TMP uv run python -c "
import sys
import distill
distill.doctor = lambda *a, **k: type('R', (), {'ok': True, 'failure_reason': ''})()
sys.exit(distill.main(['test_video', 'knowledge_base', '--dry-run-payload']))
"
test -f "$TMP/test_video/payload.json"

echo "=== DoD: legacy download_transcript.py ==="
# Soft check: legacy CLI must still load and run end-to-end on a real URL when
# the network is available. Offline behaviour is covered by
# tests/test_download_transcript_legacy.py.
YT_GENERATED_DATA_DIR=$TMP uv run python download_transcript.py "https://www.youtube.com/watch?v=KE39P4qBjDk" || true

echo "=== DoD: resumability ==="
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6
rm -f "$TMP"/test_video/frames/*.jpg | head -1
YT_GENERATED_DATA_DIR=$TMP uv run python extract.py tests/fixtures/test_video.mp4 --max-frames 6

echo "=== DoD: no TODO/XXX in shipped source ==="
! grep -rn -E "(TODO|XXX)" --include="*.py" extract.py distill.py run.py clean.py models.py frame_ocr.py frame_select.py manifest.py transcript.py enrichment.py payload.py citation.py distill_render.py

echo "=== DoD complete ==="
