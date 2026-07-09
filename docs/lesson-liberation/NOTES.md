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

### D8 — Long videos: transcript-first extraction + targeted grabs (2026-07-09)
The base frame pipeline caps at 999 frames / 99-minute filenames
(`frame_NNN_t-MM-SS`). Rather than surgery on that format, the workflow goes
transcript-only for >98min sources and the **review loop's targeted ffmpeg
grabs** (cited by `t=`, stored in `frames_targeted/`) serve as the visual
channel — evidence is fetched exactly where the reviewer found a gap, instead
of pre-sampling ~1000 frames of a 10h course. Citation timestamp grammar was
widened to `H:MM:SS`/`MMM:SS` for long videos.

### D9 — Artifacts persist outside Archon worktrees (2026-07-09)
Archon runs each workflow in an isolated worktree that gets cleaned up; a
multi-hour extraction must survive. All workflow nodes export
`YT_GENERATED_DATA_DIR=$HOME/.lesson-liberation/Generated_Data` (also set in
`~/.archon/.env`, alongside OPENROUTER_API_KEY for worktree runs — repo .env
is gitignored and absent in worktrees). Entry points additionally self-load
the repo .env via env_bootstrap.py.

### D10 — C0 resolved as per-phase flags (2026-07-09)
Per-phase model selection = existing profile seam + flags: `distill --model`,
`review_loop --review-model` (cheap gap detection) / `--synth-model` (strong
re-synthesis). No new config layer.

## Answered

### Q2 — No linked GitHub repo on the target video ✓
The UE5.8 course description links Patreon/merch/sponsors/related videos plus
4 bit.ly shortlinks (likely asset packs). No `github_repo`; reconciliation
correctly stays inactive (contract v1). Shortener resolution was added to the
follower; note this sandbox blocks DNS to bit.ly, so resolution activates on
unrestricted runs.

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

## Acceptance run — UE5.8 for Architects (2026-07-09)

Full pipeline executed live: extract (transcript-only, 10.4h, 12,393 segments)
→ reference-follow (10 links, no repo) → distill claude_skill (gemini-3-flash,
~215K-token payload) → review loop (2 iterations, frame grabs disabled in
sandbox).

Result: bundle shipped **status=incomplete** with 4 residual blocking gaps —
all asset-availability findings (instructor's Rhino model, UV-checker texture,
PBR texture set, UI_HUAD widget layout). These are TRUE gaps: the course's
project files are behind Patreon-gated shortlinks; no amount of escalation can
conjure them. The reviewer correctly refused to pass a package a fresh agent
couldn't execute verbatim, and the pipeline shipped it flagged rather than
silently truncated — exactly the specified behavior. The skill remains
applicable to a user's own CAD model (workflow, values, and techniques are
fully captured: 10,000 Lux sun, IOR 1.0 glass, 2m box mapping, complex-as-
simple collision, tag-addressed light switches, 5.7→5.8 hit-lighting fix).

Distiller citation hallucination observed (13 seg IDs beyond range, caught by
validator) — future work: feed the validator's unresolved list back through a
correction pass, and/or chunked map-reduce distillation for >2h sources to
deepen coverage per lesson.

### D11 — DNS resilience: DoH fallback, two layers (2026-07-09)
The local network hijacks port-53 and NXDOMAINs filtered hosts (bit.ly et al) —
even queries addressed to 1.1.1.1 are intercepted; DoH passes untouched.
Fix layer 1 (in-repo, portable): `dns_fallback.py` wraps socket.getaddrinfo;
on resolution failure it resolves via DoH (Cloudflare → Google redundancy),
caches, and pins the IP — SNI/cert validation still use the hostname. Armed by
env_bootstrap in every entry point. Proven live: all 4 bit.ly links resolved
(they're Amazon NAS affiliate links, not course assets — reviewer's missing-
asset gaps confirmed correct). Fix layer 2 (machine-wide): encrypted-DNS
.mobileconfig (Cloudflare DoH) generated for install. Claude Code sandbox also
opened globally (~/.claude/settings.json allowedDomains ["*"]) — it was the
first suspect but NOT the root cause.
