# youtube-transcripts — Decisions

### DEC-001: Vendor claude-video privately (vs submodule, fork, or skill install)

- **Date**: 2026-05-07
- **Context**: The `bradautomates/claude-video` repo provides frame extraction + Whisper + yt-dlp wrappers we need for the merge. We could submodule it, fork it, install it as a Claude skill, or vendor it.
- **Decision**: Vendor. Copy the five `scripts/*.py` plus LICENSE + UPSTREAM.md into `vendor/claude_video/` (underscore directory name to allow Python imports).
- **Alternatives**:
  - Submodule — rejected: importing across submodule boundary in Python is awkward.
  - Fork — rejected: discards useful upstream structure for no real gain.
  - Skill install — rejected: user wanted everything in-repo, not as a separate distributable.

### DEC-002: Use private functions from vendored whisper module

- **Date**: 2026-05-07
- **Context**: `vendor/claude_video/scripts/whisper.py` exposes only `transcribe_video(video_path, audio_out, ...)` publicly. We pass already-extracted audio (from elsewhere in the pipeline), so calling the public function would trigger a redundant ffmpeg pass on the audio file itself.
- **Decision**: `transcript.py::_fetch_via_whisper` calls `_post_whisper` and `_segments_from_response` directly. This relies on private API but the vendored copy is frozen — these names won't change without an explicit re-vendor.
- **Alternatives**:
  - Pay the redundant ffmpeg cost — rejected: noticeably slower and more disk I/O for no benefit.
  - Patch the vendored module to expose a public `transcribe_audio(...)` — rejected for v1 (vendoring discipline is "no modifications"); revisit if re-vendoring.

### DEC-003: Two-phase pipeline with `extract.py` then `distill.py`

- **Date**: 2026-05-07
- **Context**: The merged tool needs to support re-distilling with different style guides without re-downloading. Single command vs split.
- **Decision**: Two-phase. `extract.py` produces `Generated_Data/<title>/` with manifest + frames + OCR + transcript. `distill.py` consumes that. `run.py` chains both for one-shot use.
- **Alternatives**: Single command (rejected — re-styling would re-run everything); skill packaging (rejected — user wanted in-repo).

### DEC-004: Strict subagent-driven execution with two-stage review per task

- **Date**: 2026-05-07
- **Context**: Implementation plan has 38 bite-sized tasks. Review options ranged from no review to a single combined review to dual reviewers (spec compliance + code quality).
- **Decision**: Dual reviewers per task. Spec reviewer first (verifies code matches plan), code quality reviewer second (scrutinizes craftsmanship). Fix loops on either reviewer's findings.
- **Alternatives**: Single combined review (rejected — would conflate "did you build the right thing?" with "did you build it well?"); skip review on trivial tasks (rejected — typos and deprecation warnings caught by review on small tasks 1.1, 1.4, 2.2 prove the value).
- **Outcome (M1-M3 retrospective)**: Caught one critical typo (`openrouter.io` vs `.ai`), one deprecation warning (`datetime.utcnow`), one misleading test name. All would have shipped without the review pass.
