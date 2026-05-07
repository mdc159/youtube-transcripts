# youtube-transcripts — Project Context

## Active work

- [2026-05-07] **Active feature branch:** `feat/claude-video-merge` — merging the `bradautomates/claude-video` repo into this one for frame-extraction + multimodal distillation. **Status:** M3 of 10 milestones complete (HEAD `4fc1b79`). Resume at M4 Task 4.1 (`frame_ocr.py` with RapidOCR per-frame).
- Spec: `docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`
- Plan: `docs/superpowers/plans/2026-05-07-youtube-transcripts-claude-video-merge.md`
- Execution mode: subagent-driven (fresh subagent per task + spec review + code-quality review).

## Notes

- [2026-05-07] **Python pin:** `requires-python = ">=3.11,<3.13"`. The lower bound is forced by `rapidocr-onnxruntime`'s `onnxruntime` wheels (cp311+ only). `.python-version` is `3.12`.
- [2026-05-07] **Vendored claude_video at `vendor/claude_video/`** (note underscore — Python imports). Pinned to upstream commit `755c157466738dda102c939158a0116b972925a3`. See `vendor/claude_video/UPSTREAM.md`. **Modifications: none.** Future patches must be tracked there.
- [2026-05-07] **Vendored whisper API:** `vendor/claude_video/scripts/whisper.py` exposes only `transcribe_video(video_path, audio_out, ...)` publicly — there is NO public function that accepts pre-extracted audio. `transcript.py::_fetch_via_whisper` deliberately uses the *private* `_post_whisper` and `_segments_from_response` to skip a redundant ffmpeg pass. This was reviewed and accepted; if upstream is re-vendored later, audit the adapter.
- [2026-05-07] **pytest `integration` marker** is pre-declared in `pyproject.toml`'s `[tool.pytest.ini_options]`. Use `@pytest.mark.integration` on E2E tests (M6 onward) — no warnings.
- [2026-05-07] **Subagent-driven execution scale:** running ~3 milestones (≈9 tasks × 4-6 dispatches each) is the practical session ceiling before context cache pressure compounds. Plan to checkpoint at milestone boundaries and resume in fresh sessions.
- [2026-05-07] **Models config:** `models.yaml` at repo root. Default `gemini-3-flash`. Resolution: CLI > `DISTILL_MODEL` env > `default` field. Adding a new vision model is one YAML entry, zero code changes. **Note:** OpenRouter URLs are `openrouter.ai` — the typo `openrouter.io` was caught and fixed once already; double-check on additions.

## Reference

- [2026-05-07] **Test scaffold:** `tests/` with `conftest.py` exposing fixtures `fixtures_dir`, `repo_root`, `tmp_generated_data`. Integration tests live in `tests/integration/`.
