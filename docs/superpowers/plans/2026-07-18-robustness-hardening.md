# Robustness Hardening Implementation Plan (Sub-project 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Orchestration mode:** Claude orchestrates via the `herdr-fleet` interactive pattern — boot a `codex` pane (GPT-5.6-sol), wait idle, submit ONE task, supervise with short wait+read rounds, answer `blocked` prompts. Workers may run tests if their sandbox permits (orchestrator answers approval prompts); the orchestrator ALWAYS re-verifies and commits. Spec: `docs/superpowers/specs/2026-07-18-robustness-hardening-design.md`.

**Goal:** Eliminate the 8-test Windows baseline (P1), add retry resilience to every external call (P2), and make failures typed and legible (P3) — zero functionality loss.

**Architecture:** Mechanical UTF-8 + POSIX-path sweeps at I/O boundaries; new `core/errors.py` (typed hierarchy rooted at RuntimeError) and `core/llm.py` (single client factory + backoff retry) replacing three duplicated call sites; `requests` Session+Retry for reference fetches; argparse-level validation in the CLI.

**Tech Stack:** Python 3.11–3.12, uv, pytest, openai SDK (OpenRouter), requests/urllib3.

## Global Constraints

- Baseline at plan start: 8 failing tests (golden ×4, distill_live, reconcile ×2, reference_follower). Tasks 1–2 REMOVE these from the baseline; after Task 2 the expected failure count is **0** and stays 0.
- Zero functionality loss; artifact formats unchanged except path-separator normalization (which is the *documented* format — Linux already produced forward slashes).
- Helpers raise `YtDistillError` subclasses (never SystemExit); every subclass derives from RuntimeError.
- Test with `uv run pytest` (orchestrator) or `.venv\Scripts\python.exe -m pytest` (worker fallback if uv is sandbox-blocked).
- Never touch `vendor/` or `.venv/`. Never commit `media_cache/` changes (`git checkout -- media_cache/`).
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: UTF-8 everywhere

**Files:**
- Modify: every file under `src/yt_distill/` and `scripts/` with unencoded text I/O (~54 sites; enumerate with the grep below)
- Modify: `src/yt_distill/cli.py` (stdout/stderr reconfigure)
- Test: existing suite — `tests/integration/test_golden.py` ×4 and `tests/test_distill_live.py` flip green; no new test files

**Interfaces:**
- Consumes: nothing. Produces: no API changes — byte-level behavior only.

- [ ] **Step 1: Enumerate every unencoded text I/O site**

```bash
grep -rnE "\.read_text\(\)|\.write_text\(|(^|[^_a-z])open\(" --include="*.py" src/ scripts/ | grep -v "encoding=" | grep -vE "'rb'|\"rb\"|'wb'|\"wb\"|'ab'|\"ab\""
```

- [ ] **Step 2: Fix every site**

Rules: `p.read_text()` → `p.read_text(encoding="utf-8")`; `p.write_text(x)` → `p.write_text(x, encoding="utf-8")`; text-mode `open(...)` gains `encoding="utf-8"`. Binary modes stay untouched. Do not alter any other argument or reflow code.

- [ ] **Step 3: Console reconfigure in cli.py**

Insert at the top of `main()` in `src/yt_distill/cli.py`:

```python
    # Windows consoles default to cp1252; artifact text is UTF-8 (⚠, —, etc.).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
```

- [ ] **Step 4: Verify — the encoding baseline flips green**

Run: `uv run pytest tests/integration/test_golden.py tests/test_distill_live.py -q`
Expected: golden ×4 PASS; distill_live PASS (its failure was the ⚠ print — if it still fails, the remaining cause is Task 2's path work; report, don't chase).
Then full suite: expected failures shrink to ONLY the 3 path-separator tests (reconcile ×2, reference_follower).

- [ ] **Step 5: Golden byte-compare**

Run: `uv run python scripts/regen_golden_payloads.py && git status --porcelain tests/fixtures`
Expected: EMPTY (Windows now regenerates goldens byte-identically). Restore any `media_cache/` noise.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "fix: utf-8 encoding on all text I/O + console reconfigure (P1a, P1b)"
```

---

### Task 2: POSIX path normalization at artifact boundaries

**Files:**
- Modify: `src/yt_distill/core/reconcile.py` (repo-relative paths in citations/`reconciliation.json`)
- Modify: `src/yt_distill/stages/references.py` (snapshot file maps)
- Inspect (change only if os-native separators leak): `src/yt_distill/core/citation.py`, `src/yt_distill/stages/frame_ocr.py` (ocr.json frame paths)
- Test: existing `tests/test_reconcile.py`, `tests/test_reference_follower.py` flip green

**Interfaces:**
- Produces: all artifact-embedded relative paths use `/` regardless of OS. Filesystem access still uses `Path` natively.

- [ ] **Step 1: Find the leak sites**

```bash
grep -rnE "relative_to|os\.path\.rel|rglob|glob|str\(.*path" --include="*.py" src/yt_distill/core/reconcile.py src/yt_distill/stages/references.py | head -30
```

Read each hit: wherever a relative path is stringified INTO an artifact dict/JSON/citation (not used to open a file), wrap with `.as_posix()` — e.g. `str(p.relative_to(root))` → `p.relative_to(root).as_posix()`.

- [ ] **Step 2: Verify the three path tests**

Run: `uv run pytest tests/test_reconcile.py tests/test_reference_follower.py -q`
Expected: ALL PASS.

- [ ] **Step 3: Full suite — the baseline is dead**

Run: `uv run pytest -q`
Expected: **0 failed**. This is the P1 exit criterion; if anything still fails, STOP and report.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "fix: POSIX separators for artifact-embedded paths (P1c, P1d)"
```

---

### Task 3: Typed exception hierarchy

**Files:**
- Create: `src/yt_distill/core/errors.py`
- Modify: `src/yt_distill/cli.py` (catch + exit-code mapping)
- Test: `tests/test_errors.py` (new)

**Interfaces:**
- Produces (Tasks 4–6 and sub-project 3 rely on these exact names): `YtDistillError(RuntimeError)`; subclasses `TranscriptError, ExtractError, DistillError, CitationError, RefFollowError, LLMError, ModelConfigError` — all in `yt_distill.core.errors`.

- [ ] **Step 1: Write failing tests** — `tests/test_errors.py`:

```python
"""Typed error hierarchy: catchable as RuntimeError, distinguishable by type."""
import pytest

from yt_distill.core import errors
from yt_distill import cli

ALL = [errors.TranscriptError, errors.ExtractError, errors.DistillError,
       errors.CitationError, errors.RefFollowError, errors.LLMError,
       errors.ModelConfigError]


@pytest.mark.parametrize("exc", ALL)
def test_subclasses_are_runtime_and_ytdistill_errors(exc):
    assert issubclass(exc, errors.YtDistillError)
    assert issubclass(exc, RuntimeError)  # legacy `except RuntimeError` still works


def test_cli_maps_ytdistill_error_to_exit_1(mocker, capsys):
    mocker.patch("yt_distill.clean.main",
                 side_effect=errors.DistillError("style 'bogus' not found"))
    rc = cli.main(["clean"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "style 'bogus' not found" in err
    assert "Traceback" not in err


def test_cli_lets_unexpected_exceptions_raise(mocker):
    mocker.patch("yt_distill.clean.main", side_effect=ValueError("bug"))
    with pytest.raises(ValueError):
        cli.main(["clean"])
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_errors.py -q` → FAIL (no module `errors`).

- [ ] **Step 3: Implement** — `src/yt_distill/core/errors.py`:

```python
"""Typed error hierarchy.

Every class derives from RuntimeError so existing `except RuntimeError`
call sites keep working; the CLI maps YtDistillError to a clean one-line
message + exit 1, while unexpected exceptions still traceback (bugs should
be loud).
"""
from __future__ import annotations


class YtDistillError(RuntimeError):
    """Base for all predictable pipeline failures."""


class TranscriptError(YtDistillError): ...
class ExtractError(YtDistillError): ...
class DistillError(YtDistillError): ...
class CitationError(YtDistillError): ...
class RefFollowError(YtDistillError): ...
class LLMError(YtDistillError): ...
class ModelConfigError(YtDistillError): ...
```

In `src/yt_distill/cli.py`, wrap the dispatch call:

```python
    from yt_distill.core.errors import YtDistillError
    try:
        rc = getattr(module, attr)(prefix + rest)
    except YtDistillError as exc:
        print(f"yt-distill {cmd}: {exc}", file=sys.stderr)
        return 1
    return 0 if rc is None else int(rc)
```

- [ ] **Step 4: Verify** — `uv run pytest tests/test_errors.py tests/test_cli.py -q` → PASS; full suite 0 failed.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: typed error hierarchy + CLI mapping (P3)"`

---

### Task 4: Central LLM client with retries + reasoning_effort

**Files:**
- Create: `src/yt_distill/core/llm.py`
- Modify: `src/yt_distill/pipeline/distill.py` (~line 214), `src/yt_distill/stages/visual.py` (~line 312), `src/yt_distill/core/models.py` (~line 110) — replace inline `OpenAI(...)`/`client.chat.completions.create(...)` with `llm.make_client`/`llm.chat_completion`
- Test: `tests/test_llm.py` (new)

**Interfaces:**
- Consumes: `Profile` (has `base_url`, `api_key_env`, `model`, `reasoning_effort`), `errors.LLMError`, `errors.ModelConfigError`.
- Produces: `make_client(profile) -> OpenAI`; `chat_completion(profile, *, client=None, max_attempts=3, **create_kwargs) -> response`. `create_kwargs` pass through verbatim (messages, max_tokens, etc.); `model` is filled from the profile if absent; `reasoning_effort` adds `extra_body={"reasoning": {"effort": ...}}` merged over any caller-provided extra_body.

- [ ] **Step 1: Write failing tests** — `tests/test_llm.py`:

```python
"""Central LLM client: retry policy + reasoning_effort wiring."""
import pytest

import openai
import httpx

from yt_distill.core import llm
from yt_distill.core.errors import LLMError
from yt_distill.core.models import resolve


def _fake_request():
    return httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _rate_limit():
    return openai.RateLimitError(
        "429", response=httpx.Response(429, request=_fake_request()), body=None)


class FlakyClient:
    """Fails n times with the given error, then returns a sentinel."""
    def __init__(self, fails, error_factory):
        self.calls = 0
        self._fails, self._factory = fails, error_factory
        self.kwargs = None
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.calls += 1
        if self.calls <= self._fails:
            raise self._factory()
        return {"ok": True}


@pytest.fixture(autouse=True)
def _no_sleep(mocker):
    mocker.patch("yt_distill.core.llm.time.sleep")


def test_transient_error_retried_then_succeeds():
    c = FlakyClient(fails=2, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    out = llm.chat_completion(prof, client=c, messages=[])
    assert out == {"ok": True}
    assert c.calls == 3


def test_attempts_exhausted_raises_llmerror():
    c = FlakyClient(fails=5, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    with pytest.raises(LLMError):
        llm.chat_completion(prof, client=c, messages=[])
    assert c.calls == 3  # default max_attempts


def test_non_transient_raises_immediately():
    def auth_err():
        return openai.AuthenticationError(
            "401", response=httpx.Response(401, request=_fake_request()), body=None)
    c = FlakyClient(fails=5, error_factory=auth_err)
    prof = resolve("gemini-3.5-flash")
    with pytest.raises(LLMError):
        llm.chat_completion(prof, client=c, messages=[])
    assert c.calls == 1


def test_reasoning_effort_wired_into_extra_body():
    c = FlakyClient(fails=0, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash-high")
    llm.chat_completion(prof, client=c, messages=[])
    assert c.kwargs["extra_body"]["reasoning"] == {"effort": "high"}
    assert c.kwargs["model"] == prof.model


def test_no_reasoning_effort_no_extra_body_key():
    c = FlakyClient(fails=0, error_factory=_rate_limit)
    prof = resolve("gemini-3.5-flash")
    llm.chat_completion(prof, client=c, messages=[])
    assert "reasoning" not in (c.kwargs.get("extra_body") or {})
```

- [ ] **Step 2: Verify failure** — `uv run pytest tests/test_llm.py -q` → FAIL (no module `llm`).

- [ ] **Step 3: Implement** — `src/yt_distill/core/llm.py`:

```python
"""Central LLM client: one place for client construction, retries, and
profile-driven request shaping (reasoning effort).

Retry policy: transient failures (rate limits, 5xx, timeouts, connection
drops) back off exponentially with jitter for `max_attempts` tries, then
raise LLMError. Non-transient failures (auth, bad request) raise LLMError
immediately — retrying them only burns time.
"""
from __future__ import annotations

import os
import random
import time

import openai
from openai import OpenAI

from yt_distill.core.errors import LLMError, ModelConfigError

TRANSIENT = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


def make_client(profile) -> OpenAI:
    api_key = os.environ.get(profile.api_key_env)
    if not api_key:
        raise ModelConfigError(
            f"missing API key: set {profile.api_key_env} for profile {profile.name}")
    return OpenAI(base_url=profile.base_url, api_key=api_key)


def chat_completion(profile, *, client=None, max_attempts: int = 3, **create_kwargs):
    client = client or make_client(profile)
    create_kwargs.setdefault("model", profile.model)
    effort = getattr(profile, "reasoning_effort", None)
    if effort:
        extra = dict(create_kwargs.get("extra_body") or {})
        extra["reasoning"] = {"effort": effort}
        create_kwargs["extra_body"] = extra

    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**create_kwargs)
        except TRANSIENT as exc:
            last = exc
            if attempt == max_attempts:
                break
            delay = (2 ** (attempt - 1)) * (0.5 + random.random())
            print(f"[llm] transient {type(exc).__name__}, retry {attempt}/{max_attempts - 1} in {delay:.1f}s")
            time.sleep(delay)
        except openai.OpenAIError as exc:
            raise LLMError(f"LLM call failed ({type(exc).__name__}): {exc}") from exc
    raise LLMError(
        f"LLM call failed after {max_attempts} attempts ({type(last).__name__}): {last}") from last
```

- [ ] **Step 4: Rewire the three call sites.** In `pipeline/distill.py` and `stages/visual.py`: build kwargs as today, call `llm.chat_completion(profile, **kwargs)` (delete local `OpenAI(...)` + api-key checks — `make_client` owns those; keep their surrounding error handling). In `core/models.py` doctor: use `llm.make_client(profile)` for construction but keep DIRECT `client.chat.completions.create` calls — probes must observe raw failures, not retry.

- [ ] **Step 5: Verify** — `uv run pytest tests/test_llm.py -q` PASS, then full suite 0 failed, then live: `uv run yt-distill doctor --profile gemini-3.5-flash-high` → ok=True (now actually sending effort).

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: central LLM client with backoff retries + reasoning_effort (P2a, P2c)"`

---

### Task 5: HTTP retries for reference following

**Files:**
- Modify: `src/yt_distill/stages/references.py`
- Test: `tests/test_reference_follower.py` (append one test)

**Interfaces:**
- Produces: module-level `_session() -> requests.Session` used for all GET fetches in references.py.

- [ ] **Step 1: Append failing test** to `tests/test_reference_follower.py` (match its import style):

```python
def test_fetch_session_retries_on_5xx():
    from yt_distill.stages import references
    s = references._session()
    adapter = s.get_adapter("https://example.com")
    r = adapter.max_retries
    assert r.total >= 3 and r.backoff_factor > 0
    assert 502 in r.status_forcelist and 429 in r.status_forcelist
```

- [ ] **Step 2: Implement.** In `references.py` add:

```python
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter


def _session() -> requests.Session:
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=(408, 425, 429, 500, 502, 503, 504),
                  allowed_methods=("GET", "HEAD"), respect_retry_after_header=True)
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s
```

Replace every `requests.get(...)` in the module with a shared `_session().get(...)` (construct once at call boundary or module level — read the code and match its structure).

- [ ] **Step 3: Verify** — targeted test PASS; full suite 0 failed.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat: retrying HTTP session for reference fetches (P2b)"`

---

### Task 6: CLI input validation

**Files:**
- Modify: `src/yt_distill/cli.py` (pre-dispatch validation)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `errors.YtDistillError`. Produces: validation before dispatch for `extract`/`run` (source) and `distill`/`review`/`refs`/`enrich` (title dir).

- [ ] **Step 1: Append failing tests** to `tests/test_cli.py`:

```python
def test_extract_rejects_nonexistent_source(capsys):
    rc = cli.main(["extract", "no_such_file.mp4"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_extract_accepts_url_shapes(mocker):
    m = mocker.patch("yt_distill.pipeline.extract.main", return_value=0)
    assert cli.main(["extract", "https://youtu.be/EnXKysJNz_8"]) == 0
    m.assert_called_once()


def test_distill_rejects_missing_title_dir(capsys):
    rc = cli.main(["distill", "definitely_missing_dir", "coding_agent"])
    assert rc == 1
    assert "artifact" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Implement.** In `cli.py` before dispatch: for `extract`/`run`, the first non-flag arg must be an existing file OR match `^https?://|^youtu\.be/|youtube\.com/`; else raise `YtDistillError(f"source not found and not a URL: {src} — pass an existing file or a http(s)/YouTube URL")`. For `distill`/`review`/`refs`/`enrich`, resolve the title dir the same way the pipeline does (`YT_GENERATED_DATA_DIR` env or `Generated_Data/`, absolute paths as-is) and require `artifact_manifest.json` inside; else raise `YtDistillError(f"no artifact_manifest.json in {dir} — run 'yt-distill extract' first")`. Only validate when the arg is present and not `-h`/`--help`; never duplicate the subcommand's own argparse errors.

- [ ] **Step 3: Verify** — `uv run pytest tests/test_cli.py -q` PASS; full suite 0 failed.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat: CLI input validation with actionable messages (P3)"`

---

### Task 7: Final verification gate (ORCHESTRATOR-RUN)

- [ ] **Step 1:** `uv run pytest` → **0 failed** (P1 headline). `uv run pytest -m integration` → 0 failed.
- [ ] **Step 2:** `uv run python scripts/regen_golden_payloads.py` → `git status --porcelain tests/fixtures` EMPTY.
- [ ] **Step 3:** `bash scripts/dod_check.sh` → fully green, end to end, on Windows (first time ever).
- [ ] **Step 4 — live artifact for external evaluation:** `uv run yt-distill run "https://youtu.be/EnXKysJNz_8" auto` (persistent default output — NO temp dir). Verify exit 0, zero unresolved citations. **Report the exact `Generated_Data/<title>/` path and final markdown filename to Mike** — a separate agent evaluates it.
- [ ] **Step 5 — idempotency:** re-run the same command; extract phase must skip completed work (manifest hashes).
- [ ] **Step 6:** honest gate report; update plan ledger + Obsidian mirror; Honcho conclusion.
