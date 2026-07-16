# Modular Restructure & Stage Architecture — Design

**Date:** 2026-07-16
**Status:** Approved design, pending implementation plan
**Sub-project:** 1 of 3 (restructure → robustness → north-star features)

## North star (context for all three sub-projects)

Point the tool at one or more sources (e.g. a 5-hour Unreal Engine YouTube
tutorial) and distill it — per video type (lesson, step-by-step instructional,
physical build with bill of materials) — into a **self-sufficient artifact**:
a durable skill (or several) that an agent or a human can use to complete the
taught workflows end-to-end, without rewatching the video.

Two standing principles:

1. **Zero functionality loss.** Every style, artifact format, and flag
   survives every refactor. The styles (`styles/*.md`) are explicitly
   protected. Deletions require documented supersession.
2. **Economical-first escalation.** Start with the cheapest data-gathering
   method and escalate only when necessary. Token cost is secondary (Max plan
   covers orchestration), but *method* economy stays: free APIs before local
   compute before LLM calls before vision-LLM calls.

## Goals (this sub-project)

- Move the ~20 flat root modules into a `src/yt_distill/` package.
- Replace 8 per-file CLIs with one `yt-distill` console script (clean break —
  no compatibility shims).
- Introduce a **stage registry**: the modular core that lets new enrichment
  tools be added later as drop-in modules.
- Update the vision model profile to Gemini 3.5 Flash.
- Delete dead/superseded files (with supersession evidence, below).
- Update all docs and workflows to the new CLI.

## Non-goals (deferred to sub-projects 2 and 3)

- Robustness hardening (retries, typed errors, logging) — sub-project 2.
- Long-video chunking, multi-source input, multi-skill emission,
  self-sufficiency gate — sub-project 3. Each will land as new *stages* on
  this foundation.
- Third-party plugin entry points. The in-package registry can graduate to
  entry-point discovery later without redesign; building it now is YAGNI.

## Package layout

```
src/yt_distill/
  cli.py              # `yt-distill` console script: extract, refs, distill,
                      #   review, run, enrich, clean, doctor
  stages/             # THE modular core
    registry.py       #   Stage dataclass + registration + tier ordering
    transcript.py     #   4-tier transcript chain (from transcript.py)
    frame_ocr.py      #   from frame_ocr.py
    frame_select.py   #   from frame_select.py
    references.py     #   reference_follower.py
    visual.py         #   enrich.py tiers as registered stages
  pipeline/           # orchestrators (thin: sequence stages, own I/O)
    extract.py        #   from extract.py
    distill.py        #   from distill.py
    review.py         #   from review_loop.py
    run.py            #   from run.py
  core/               # shared building blocks
    manifest.py  citation.py  reconcile.py  payload.py
    enrichment.py  video_profile.py  models.py
    env_bootstrap.py  dns_fallback.py
  output/
    render.py         #   from distill_render.py
    skill_bundle.py   #   from skill_bundle.py
  clean.py            # from clean.py

styles/  prompts/  models.yaml   # UNCHANGED locations — styles preserved
tests/                           # same suite, imports updated
scripts/dod_check.sh             # updated to new CLI invocations
```

Move logic verbatim where possible; this is a relocation, not a rewrite.
Behavior changes are limited to the stage-registry seam and the CLI surface.

## Stage registry

Each processing/enrichment capability is a **stage** — a module that registers
a `Stage`:

```python
@dataclass(frozen=True)
class Stage:
    name: str                 # "transcript", "frame_ocr", "visual_gallery", ...
    cost_tier: CostTier       # FREE < LOCAL_COMPUTE < CHEAP_LLM < VISION_LLM
    requires: frozenset[str]  # artifact keys it needs (e.g. "video", "transcript")
    produces: frozenset[str]  # artifact keys it writes (e.g. "ocr.json")
    run: Callable[[StageContext], StageResult]
```

- `StageContext` carries the title dir, manifest, resolved model profile, and
  options. `StageResult` reports produced artifacts + diagnostics.
- The registry orders runnable stages by `cost_tier` — economical-first is
  structural, not conventional.
- Idempotency stays manifest-driven: a stage is skipped when its `produces`
  artifacts are intact in `artifact_manifest.json` (same mechanism extract.py
  uses today; the registry just generalizes the check).
- `review_loop` escalation becomes: re-enable specific stages (or higher
  thinking effort) for the gap areas the reviewer identified.
- **Adding a new enrichment tool later** = one new module in `stages/`
  registering one `Stage`. No orchestrator surgery.

Existing orchestrator logic is *wrapped* into stages, not rewritten. Scoping:
this sub-project delivers the registry itself (tested, with the contract
above) and relocates the stage modules; registering the built-in capabilities
and re-sequencing the orchestrators through the registry lands in
sub-project 3, when the first consumers (escalation control, new enrichment
tools) actually need it. Building wrappers nothing calls yet is YAGNI.

## CLI

Single console script via pyproject `[project.scripts]`:

```
yt-distill extract "<url-or-path>" [--force] [--force-ocr] [--cookies-from-browser X]
yt-distill refs <title-dir> [--max-repo-mb N] [--max-fetches N]
yt-distill distill <title-dir> <style> [--model X] [--dry-run-payload]
yt-distill review <title-dir> [--max-iterations N]
yt-distill run "<url-or-path>" <style>
yt-distill enrich <title-dir> <style> [--no-llm] [--no-mermaid] [--no-tables] [--no-mindmap]
yt-distill clean [--delete-video] [--older-than 30d] [--apply]
yt-distill doctor [--profile <name>]
```

Every existing flag is carried over 1:1. Clean break: the old
`uv run python extract.py ...` forms are removed and all call sites updated —
`README.md`, `CLAUDE.md`, `.archon/workflows/lesson-liberation.yaml`,
`.cursor/skills/*`, `scripts/dod_check.sh`.

## Model profile: Gemini 3.5 Flash

Add to `models.yaml` and make it the default:

```yaml
default: gemini-3.5-flash

profiles:
  gemini-3.5-flash:
    base_url: https://openrouter.ai/api/v1     # OpenRouter key, per Mike
    model: google/gemini-3.5-flash
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 32
    max_image_bytes: 5242880
```

Model-card facts that shape usage (verified 2026-07-16 on OpenRouter):

- 1,048,576-token context; 65,536 max output. Inputs: text, image, video,
  audio, PDF.
- Near-Pro coding/reasoning at Flash cost ($1.50/M in, $9/M out). Explicitly
  optimized for coding proficiency and agentic execution loops — a good match
  for the distill contract's cite-and-verify style.
- **Thinking effort is controllable** (minimal / low / medium / high; default
  medium) via the OpenRouter `reasoning` parameter. This maps directly onto
  the escalation principle: first-pass distills run default/low; review-loop
  escalations re-run at high. Wiring effort into `Profile` is a small
  additive field (`reasoning_effort`, optional) so profiles like
  `gemini-3.5-flash-high` are one YAML entry.

Existing `gemini-3-*` profiles remain in `models.yaml` (removing them would
break `--model` invocations; they're one-line entries).

## Deletions (with supersession evidence)

| File | Superseded by |
|---|---|
| `main.py` | Nothing — `uv init` hello-world stub, never imported |
| root `test_models.py` | `tests/test_models.py` (real suite lives in `tests/`) |
| `download_transcript.py` | Already a forwarding wrapper around `run.py` |
| `transform_transcript.py` | `distill.py` does the same transform plus citations, frames, OCR, validation |

No user-facing capability is removed. Git history preserves all four.

## Vendored code

`vendor/claude_video/` stays where it is, still pinned at `755c157`.
Only import paths in callers change.

## Error handling

Unchanged this sub-project: helpers raise `RuntimeError` (catchable), CLIs
exit non-zero with a message. The stage registry surfaces stage failures with
the stage name attached. Typed exception hierarchy is sub-project 2.

## Testing & verification gates

1. `uv run pytest` green before the first move and after every move batch.
2. Import updates are mechanical (`from manifest import` →
   `from yt_distill.core.manifest import`); tests catch misses.
3. `bash scripts/dod_check.sh` (updated to new CLI) passes end-to-end.
4. Golden-payload check: `scripts/regen_golden_payloads.py` output is
   byte-identical pre/post restructure — proves the payload pipeline is
   functionally untouched.
5. One real end-to-end run (`yt-distill run <short video> coding_agent`)
   before declaring done.

## Migration order

1. Create `src/yt_distill/` skeleton + pyproject packaging changes; keep old
   files importable until the end.
2. Move `core/` modules first (fewest dependents change), then `stages/`,
   then `pipeline/`, then `output/`, running tests after each batch.
3. Build `cli.py`; port each subcommand's argparse verbatim.
4. Update `models.yaml` (Gemini 3.5 Flash profile + default).
5. Delete legacy files and old root scripts.
6. Update docs, Archon workflow, cursor skills, dod_check.sh.
7. Full gate: pytest, dod_check, golden payloads, live smoke run.

## Roadmap (sub-projects 2 & 3, to be designed separately)

- **2 — Robustness:** retries with backoff on network/LLM calls, typed
  exception hierarchy, structured logging, input validation at CLI boundary.
- **3 — North-star features**, each as new stages/pipelines:
  long-video chapter-aware chunking + synthesis; multi-source (playlist /
  URL-set) input with cross-video dedup into one bundle; multi-skill emission
  from one tutorial; self-sufficiency gate (fresh-agent executability check,
  BOM completeness for physical builds).
