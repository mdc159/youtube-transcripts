# Coding Agent Prompt: Lesson Liberation — Delta Build on `youtube-transcripts`

## Context

The repo `mdc159/youtube-transcripts` already implements the extraction core: 4-tier transcript escalation (yt-api → pytube → yt-dlp subs → local Whisper), ffmpeg frame extraction with OCR + frame classification + code-frame clustering, a two-phase extract/distill split, a style router, structured `distill_result.json`, a citation contract, and idempotent manifest-driven runs. **Do not rebuild any of that.** Read the repo first; extend it.

## Mission

Extend the pipeline so that, given a long-form tutorial source (e.g., a multi-hour Unreal Engine YouTube walkthrough with a linked GitHub repo), it produces a **self-sufficient lesson artifact**: a Claude Code skill package complete enough that a *different* agent, on a *different* machine, with *no access to the original source*, can follow it end to end. The distilling agent and the consuming agent are never the same agent — write for the reader who has nothing but the artifact.

Execution/verification of the lesson is explicitly **out of scope**. This pipeline runs on a Mac with no Unreal Engine. The artifact will be hand-carried to a separate machine for real-world testing later. Quality assurance happens via simulated review (below), not execution.

## New Components

### 1. Reference Follower (new pipeline phase)

- Harvest URLs from video description, pinned comment, and transcript segments (record where each was found).
- Classify: github_repo | docs | asset_download | other.
- For repos: shallow-clone, pin commit SHA, snapshot README + build/setup files + files referenced in the tutorial. Store under the run's manifest directory with provenance (URL, SHA, clone date).
- For docs: fetch → markdown, stored as auxiliary sources.
- Config: max repo size, max fetch count.

### 2. Reconciliation Pass (new distill stage)

Cross-check three evidence streams: transcript, OCR'd code clusters, cloned repo code.

- Repo code is authoritative for exact syntax.
- Transcript is authoritative for intent, ordering, and rationale.
- OCR clusters bridge the two (which repo file is on screen at which timestamp).
- Conflicts are **flagged in the artifact, never silently resolved** — e.g., "video shows X at 1:34:02; repo (SHA abc123) has Y; repo is newer."
- Extends the existing citation contract: claims may now also cite `repo:path/to/file#L10-L40@SHA`.

### 3. `claude_skill` output style (new entry in styles/)

Consumes `distill_result.json` + reconciliation output. Emits:

```
skills/<slug>/
  SKILL.md          # front-matter (name, trigger-oriented description);
                    # prerequisites w/ versions; ordered lessons/steps written
                    # imperatively for an agent; code blocks (repo-sourced where
                    # available); gotchas & flagged conflicts; build manifest
  assets/           # key frames the reviewer deemed load-bearing
  reference/        # repo pointer (URL + SHA), aux docs
  provenance.json   # source URL, video date, tiers used, versions observed,
                    # review iterations, unresolved gaps
```

**Build manifest:** enumerate every artifact the instructor constructs (projects, levels, blueprints, materials, systems, devices — whatever the domain). This is the downstream acceptance checklist; every item links to its steps.

Every step carries `status: distilled` (no step is marked verified — verification happens downstream, later, elsewhere; leave the field so downstream can flip it).

### 4. `diy_project` style extension

Add structured sections to its `distill_result.json` output: `bill_of_materials` (item, qty, spec/rating, timestamp where mentioned; no sourcing/purchasing research), `tools_required`, `theory_of_operation`, `cautions`. Human-readable output, not agent-imperative.

### 5. Downstream-Hat Review Loop (new final phase — this is the quality gate)

1. Spawn a **fresh-context** LLM reviewer. Input: the artifact only. No transcript, no frames beyond those packaged, no repo beyond the snapshot, no memory of the distillation run.
2. Reviewer performs a dry-run walkthrough: for each step/lesson, narrate concretely how it would be executed; anywhere it would be *guessing* (missing value, ambiguous UI location, undefined term, code referenced but not present), emit a gap: `{step, what's missing, likely source location (timestamp/file) if inferable}`.
3. Gaps feed back into the existing escalation machinery: targeted frame grabs at flagged timestamps, repo file pulls, transcript re-reads with wider context. Re-synthesize affected sections. Re-review.
4. Loop until reviewer reports no blocking gaps, or budget/iteration cap (default 3) is hit. If capped: artifact ships marked `incomplete`, with the residual gap list embedded in provenance — never silently truncated.
5. Log every iteration (gaps found → escalations taken → resolved?) to provenance.

## Orchestration

Package the end-to-end flow as an **Archon workflow (YAML)** whose steps shell out to the repo's CLI: extract → reference-follow → distill(style) → reconcile → review-loop → package. Deterministic phase structure with validation gates between phases; the LLM supplies judgment within phases only. Each phase's node must be independently re-runnable off the cached manifest (respect the repo's existing idempotency model).

If Archon integration friction is high, deliver the same phases as a plain CLI (`liberate <url> --style claude_skill`) with the Archon YAML as a thin wrapper — the phase boundaries and gates are the requirement, Archon is the preferred host.

## Constraints

- Mac-hosted, local-first: faster-whisper, tesseract/RapidOCR, ffmpeg, yt-dlp — no cloud transcription/OCR services. LLM calls via Anthropic API, model configurable per phase (cheap for review-gap detection, strong for reconciliation/synthesis).
- Match the existing repo's conventions (Python, manifest layout, quality grades, citation validation). Extend, don't fork patterns.
- Hard budgets in config: max review iterations, max targeted frame grabs per loop, max repo clone size.
- All new outputs carry provenance sufficient to detect staleness later (dates, SHAs, versions observed on screen or in repo).
- No interactive multiple-choice prompts to the operator. If a genuine decision is needed, state your recommendation and proceed with it, logging the decision; collect open questions in a NOTES file rather than blocking.

## Acceptance Test

Run against a multi-hour Unreal Engine tutorial with a linked GitHub repo. Success: the review loop converges, and a fresh agent given only the skill package can narrate a credible, non-guessing execution plan for every build-manifest item. Real-machine execution is a later, separate evaluation.
