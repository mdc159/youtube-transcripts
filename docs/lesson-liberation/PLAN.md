# Lesson Liberation — Delta Build Plan

Delta build on `mdc159/youtube-transcripts`. Goal: given a long-form tutorial
(YouTube URL, possibly with a linked GitHub repo), produce a **self-sufficient
lesson artifact** — a Claude Code skill package a *different* agent on a
*different* machine with *no access to the source* can follow end to end.

Source spec: `~/Downloads/lesson-liberation-prompt.md` (copied to
`docs/lesson-liberation/SPEC.md`).

## Principle

Extend, don't rebuild. The extraction core (4-tier transcript, ffmpeg frames +
RapidOCR + classifier + code-frame clustering, extract/distill split, style
router, citation contract, idempotent manifests) already exists. New work hooks
into those seams and matches existing conventions (Python 3.11–3.12, `uv`,
manifest layout, citation validation, `styles/<name>.md`, `models.yaml`).

The distilling agent and the consuming agent are never the same. Write every
artifact for a reader who has *only* the artifact.

Execution/verification of the lesson is **out of scope** (this Mac has no Unreal
Engine). QA is via simulated downstream review, not execution. Every step ships
`status: distilled` — never `verified`.

## Target pipeline (Archon-orchestrated)

```
extract → reference-follow → distill(style) → reconcile → review-loop → package
```

Deterministic phase boundaries with validation gates; the LLM supplies judgment
*within* phases only. Each phase independently re-runnable off the cached
manifest (respect existing idempotency).

## Work breakdown

### C0. Foundations / provenance plumbing
- Anthropic-direct model path (spec mandates Anthropic API; repo defaults to
  OpenRouter). Add profiles + per-phase model selection. See NOTES D1.
- Provenance object shared by new phases (dates, SHAs, versions, tiers used).

### C1. Reference Follower (new pipeline phase)
- Harvest URLs from video description, pinned/top comment, transcript segments;
  record where each was found.
- Classify: `github_repo | docs | asset_download | other`.
- Repos: shallow-clone, **pin commit SHA**, snapshot README + build/setup files +
  files referenced in the tutorial; store under manifest dir with provenance
  (URL, SHA, clone date).
- Docs: fetch → markdown, stored as auxiliary sources.
- Config: `max_repo_size`, `max_fetch_count`.
- Output: `reference_follow.json` under the run dir + `reference/` snapshot tree.

### C2. Reconciliation Pass (new distill stage)
Cross-check three evidence streams: transcript, OCR'd code clusters, cloned repo
code.
- Repo code authoritative for **exact syntax**.
- Transcript authoritative for **intent, ordering, rationale**.
- OCR clusters **bridge** (which repo file on screen at which timestamp).
- Conflicts **flagged, never silently resolved**
  (e.g. "video shows X at 1:34:02; repo (SHA abc123) has Y; repo is newer").
- Extend citation contract: claims may cite `repo:path/to/file#L10-L40@SHA`.
- Output: `reconciliation.json` + conflict list feeding synthesis.

### C3. `claude_skill` output style (new `styles/` entry)
Consumes `distill_result.json` + reconciliation output. Emits:
```
skills/<slug>/
  SKILL.md          # frontmatter (name, trigger-oriented description);
                    # prerequisites w/ versions; ordered lessons/steps, imperative
                    # for an agent; repo-sourced code blocks; gotchas & flagged
                    # conflicts; build manifest
  assets/           # load-bearing key frames
  reference/        # repo pointer (URL + SHA), aux docs
  provenance.json   # source URL, video date, tiers used, versions observed,
                    # review iterations, unresolved gaps
```
- **Build manifest**: enumerate every artifact the instructor constructs
  (projects, levels, blueprints, materials, systems, devices…). Downstream
  acceptance checklist; every item links to its steps.
- Every step: `status: distilled` (leave field for downstream to flip).
- Register in style router (explicit-only, like `human_tutorial`; `auto` never
  routes here) + mirror `.cursor/skills/`.

### C4. `diy_project` style extension
Add structured sections to its `distill_result.json`:
`bill_of_materials` (item, qty, spec/rating, timestamp mentioned; no purchasing
research), `tools_required`, `theory_of_operation`, `cautions`.
Human-readable output, not agent-imperative.

### C5. Downstream-Hat Review Loop (quality gate)
1. Fresh-context reviewer; input = artifact only (no transcript/frames/repo
   beyond what's packaged, no memory of the distill run).
2. Dry-run walkthrough per step; emit gaps `{step, missing, likely source
   (timestamp/file)}` wherever it would be guessing.
3. Gaps feed existing escalation: targeted frame grabs at flagged timestamps,
   repo file pulls, wider transcript re-reads. Re-synthesize affected sections.
   Re-review.
4. Loop until no blocking gaps or cap (default 3). If capped: ship marked
   `incomplete`, residual gaps embedded in provenance — never silently truncated.
5. Log every iteration (gaps → escalations → resolved?) to provenance.

### C6. Archon workflow (orchestration)
YAML wrapping the repo CLI: `extract → reference-follow → distill(style) →
reconcile → review-loop → package`. Deterministic gates between phases; each
node re-runnable off the cached manifest. Lives in the workflow host repo
(`.archon/workflows/`). If Archon friction is high: ship a `liberate <url>
--style claude_skill` CLI with the YAML as a thin wrapper — phase boundaries +
gates are the requirement, Archon is preferred host.

## Constraints (from spec)
- Mac-hosted, local-first: faster-whisper, tesseract/RapidOCR, ffmpeg, yt-dlp —
  no cloud transcription/OCR. LLM via Anthropic API, model configurable per
  phase (cheap for gap detection, strong for reconciliation/synthesis).
- Match repo conventions. Extend, don't fork patterns.
- Hard budgets in config: max review iterations, max targeted frame grabs/loop,
  max repo clone size.
- All new outputs carry provenance sufficient to detect staleness (dates, SHAs,
  versions).
- **No interactive multiple-choice prompts to the operator.** Genuine decision →
  state recommendation, proceed, log it; collect open questions in `NOTES.md`.

## Acceptance test
Run against a multi-hour Unreal Engine tutorial with a linked GitHub repo
(target: `https://youtu.be/CnoC-v9xB_E` — "Unreal Engine 5 for Architects",
~10.4h, captions available). Success: review loop converges, and a fresh agent
given only the skill package can narrate a credible, non-guessing execution plan
for every build-manifest item. Real-machine execution is a later, separate eval.

## Build order
C0 → C1 → C3 (skill style, minimal) → C2 (reconciliation) → C5 (review loop) →
C4 (diy extension) → C6 (Archon wrap) → acceptance dry-run → live run (needs key).
Rationale: get an end-to-end skeleton emitting a skill bundle early, then deepen.
