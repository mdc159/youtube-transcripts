# Lesson Liberation — Decisions & Open Questions

Per spec: no interactive multiple-choice prompts. Genuine decisions are made
with a stated recommendation and logged here; open questions collected here
rather than blocking the build.

## Decisions

### D1 — LLM provider: OpenRouter (operator override, 2026-07-09)
Operator directive: use the OpenRouter API. The repo is already
OpenRouter-native (OpenAI SDK + base_url, profiles in `models.yaml`), so no
provider work is needed. Remaining C0 scope: per-phase model selection only —
cheap profile for review gap-detection, strong profile for
reconciliation/synthesis — via existing `--model`/profile seam per phase.
(Supersedes the earlier Anthropic-direct reading of the spec.)

### D2 — No API key present → build now, live run later
`OPENROUTER_API_KEY` not yet set. **Decision:** build and validate the full
pipeline with `--dry-run-payload` + golden fixtures + mocked LLM; defer the live
UE5 acceptance run until the key is in
`youtube-transcripts/.env`. Flagged once (non-blocking).

### D3 — Repo placement & Archon host
Base repo cloned to `Projects/lessons/youtube-transcripts/` as the working base
we extend in place. **Decision:** the Archon workflow lives in
`youtube-transcripts/.archon/workflows/lesson-liberation.yaml` so the repo stays
self-contained and portable (matches Archon's "commit workflows to your repo").
Run Archon from the repo root. New Python phase modules live at repo root
alongside `extract.py`/`distill.py`, matching the flat-module convention.

### D4 — Whisper fallback: local faster-whisper (spec) vs cloud (repo)
Spec: local-first, "no cloud transcription/OCR services"; repo's tier-4 Whisper
fallback uses Groq/OpenAI cloud. **Decision:** add a local `faster-whisper` tier
to honor the constraint, but as a **deferred** delta — the target UE5 video has
captions (tier 1 succeeds), so it is not on the critical path. Logged, not
blocking. Until then, cloud whisper stays as-is behind the caption tiers.

### D5 — OCR engine
Spec names "tesseract/RapidOCR (local)"; repo already uses RapidOCR (local). No
change needed. ✓

### D6 — Build order
C0 foundations → C1 reference-follow → C3 skill-style (minimal) → C2 reconcile →
C5 review-loop → C4 diy-extension → C6 Archon wrap → dry-run acceptance → live.
Get an end-to-end skeleton emitting a skill bundle early; then deepen each stage.

### D7 — New-phase output files live under the run's `Generated_Data/<title>/`
`reference_follow.json`, `reconciliation.json`, and the review-loop log join the
existing manifest tree so idempotency + provenance stay unified. `skills/<slug>/`
bundle is emitted by the `claude_skill` style (final package).

## Open questions (non-blocking)

### Q1 — API key + model/budget policy for the live run
Live acceptance run needs `ANTHROPIC_API_KEY`. Which Anthropic models for
cheap-vs-strong phase tiers, and what per-run token/frame budgets? Recommendation
pending; default to a cheap Haiku-class model for gap detection and a strong
Opus/Sonnet-class model for reconciliation/synthesis once key is available.

### Q2 — Does the target UE5 video have a linked GitHub repo?
"UE5 for Architects" is an archviz workflow course; it may link asset packs/docs
rather than a code repo. Reference Follower must degrade gracefully when there is
no `github_repo` (reconciliation then runs transcript+OCR only). Confirm by
harvesting the description during C1.

### Q3 — Which project "owns" the Archon run
Workflow lives in the repo (D3). Confirm whether operator wants it registered in
the running Archon server/Web UI for monitoring, or CLI-only.
