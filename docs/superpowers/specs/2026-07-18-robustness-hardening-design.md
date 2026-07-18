# Robustness Hardening — Design (Sub-project 2)

**Date:** 2026-07-18
**Status:** Approved scope (from 2026-07-16 trilogy design); this spec details it
**Predecessor:** `2026-07-16-modular-restructure-design.md` (complete)

## Goal

Make the pipeline correct and resilient on both Windows and POSIX, and make
every network/LLM interaction survive transient failure. Headline, measurable
outcome: **the 8-test pre-existing Windows baseline goes to zero** — full
pytest, golden byte-compare, and `dod_check.sh` all green on Windows.

Constraints carried forward: zero functionality loss; styles/artifacts
unchanged; helpers raise catchable errors, never SystemExit.

## Items (priority order)

### 1. UTF-8 everywhere (kills the mojibake class)
- Every text-mode `open()`, `Path.read_text()`, `Path.write_text()` in
  `src/` and `scripts/` gets `encoding="utf-8"` (~54 sites, mechanical).
- CLI entry (`cli.py:main`) reconfigures `sys.stdout`/`sys.stderr` to UTF-8
  (`errors="replace"`) so `⚠`-style output can't crash on cp1252 consoles
  (the `test_distill_live` UnicodeEncodeError).
- Golden fixtures stay byte-identical to their committed (correct, UTF-8)
  content — the fix makes Windows *produce* what Linux already produced.

### 2. POSIX path normalization at artifact boundaries
- Any repo-relative or artifact-relative path written into artifacts or
  citations (`repo:path#Lx-Ly@SHA` cites, `reconciliation.json`, snapshot
  file maps in reference following, `ocr.json` frame paths) is normalized to
  forward slashes (`PurePosixPath`/`as_posix()`) at the write/compare
  boundary. OS-native paths remain for actual filesystem access.
- Fixes `test_reconcile` ×2 (`repo:src\scene.py`) and
  `test_reference_follower` (`KeyError: 'src/main.py'`).

### 3. Central LLM client + retries + reasoning_effort wiring
- New `src/yt_distill/core/llm.py`: `make_client(profile)` +
  `chat_completion(profile, **kwargs)` used by `pipeline/distill.py`,
  `stages/visual.py`, and `core/models.py` (doctor keeps its single-probe
  semantics — probes get `max_retries=1`).
- Retry transient failures (HTTP 408/425/429/5xx, connection/timeout errors)
  with exponential backoff + jitter; default 3 attempts; non-transient errors
  raise immediately. Terminal failure raises `LLMError` with the last cause.
- When `profile.reasoning_effort` is set, send OpenRouter's
  `reasoning: {"effort": ...}` via `extra_body` — completes the Task 7 field.

### 4. Typed exception hierarchy (backward compatible)
- `src/yt_distill/core/errors.py`: `YtDistillError(RuntimeError)` base;
  subclasses `TranscriptError`, `ExtractError`, `DistillError`,
  `CitationError`, `ReferenceError` (named `RefFollowError` to avoid
  shadowing the builtin), `LLMError`, `ModelConfigError`.
- Deriving from RuntimeError keeps every existing `except RuntimeError`
  caller working. Helpers switch their raises to the specific type.
- `cli.py` catches `YtDistillError` → clean one-line stderr message + exit 1
  (unexpected exceptions still traceback).

### 5. HTTP retries for reference following + transcript fetches
- `requests.Session` with `urllib3.util.Retry` (3 total, backoff 0.5,
  respect Retry-After, only idempotent GET/HEAD) used by
  `stages/references.py`; transcript tier fetches keep their existing
  tier-fallback semantics (a tier failing → next tier IS the retry policy;
  no inner retry loops that would slow the chain).

### 6. Input validation at the CLI boundary
- `extract`/`run`: reject a source that is neither an existing local file nor
  a http(s)/youtu.be URL with a clear message before any work.
- `distill`/`review`/`refs`/`enrich`: verify the title dir exists and holds
  `artifact_manifest.json`; unknown style names list available styles.

### Non-goals
- No logging framework migration (print-based progress is the CLI's UX;
  revisit only if a real need appears).
- No new pipeline features (sub-project 3).
- No test-suite restructuring beyond what the fixes require.

## Execution model

Codex workers (GPT-5.6-sol) via the `herdr-fleet` interactive pattern:
`pane split` → boot `codex` → wait idle → submit task → supervise with short
wait+read rounds, answering `blocked` prompts (this restores worker-side
test runs and commits when approvals allow; else orchestrator verifies).
Kimi K3 (`moonshotai/kimi-k3`, key from sys env `OPENROUTER_API_KEY`) is
available for cross-model review later — not the workhorse for now.

## Verification gate
1. Full `uv run pytest` on Windows: **0 failures** (baseline eliminated).
2. `uv run python scripts/regen_golden_payloads.py` → `git status` clean
   (byte-identical goldens on Windows).
3. `bash scripts/dod_check.sh` fully green on Windows.
4. Live end-to-end on the real test video
   `https://youtu.be/EnXKysJNz_8` : `uv run yt-distill run <url> auto`
   completes with zero unresolved citations; then a second run to confirm
   idempotent skip behavior.
5. Retry behavior unit-tested with a mocked flaky client (no live-fail
   simulation needed).
