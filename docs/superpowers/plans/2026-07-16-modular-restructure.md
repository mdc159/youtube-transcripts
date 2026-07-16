# Modular Restructure & Stage Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.
>
> **Orchestration mode for this plan:** Claude acts as the orchestrating agent and dispatches one Codex worker per task (fork-terminal / multi-model-orchestration). Each task below is written to be fully self-contained for a worker that has NEVER seen this repo or this plan's other tasks. The orchestrator reviews the diff and test output after every task before dispatching the next.


> **COMPLETED 2026-07-16.** All 10 tasks landed (commits cb32ce8..820a94b + gate).
> Execution notes: Codex workers (GPT-5.6-sol via Herdr panes) did edits only —
> sandbox blocks network/python/git — orchestrator ran tests and committed.
> The "suite green" assumption was corrected to an 8-test pre-existing Windows
> baseline (path separators + cp1252 encoding); failure set was byte-identical
> after every task. Golden byte-compare blocked by the same pre-existing
> mojibake bug (prompt/style reads missing encoding="utf-8") — first item for
> sub-project 2. Live smoke run via gemini-3.5-flash passed with zero
> unresolved citations.

**Goal:** Move the flat-root pipeline into a `src/yt_distill/` package with a stage registry and a single `yt-distill` CLI, with zero functionality loss.

**Architecture:** Verbatim module relocation into `core/` / `stages/` / `pipeline/` / `output/` subpackages, a new pure-function stage registry (`stages/registry.py`) that orders capabilities economical-first, and a thin argparse dispatcher (`cli.py`) that forwards to the existing per-module `main(argv)` functions. Spec: `docs/superpowers/specs/2026-07-16-modular-restructure-design.md`.

**Tech Stack:** Python 3.11–3.12, uv, hatchling (src layout), pytest.

## Global Constraints

Every task's requirements implicitly include this section.

- **Zero functionality loss.** `styles/`, `prompts/`, `models.yaml` locations and `Generated_Data/` artifact formats are UNCHANGED. Every existing CLI flag survives 1:1.
- **Relocation, not rewrite.** Moved modules keep their code verbatim except import lines. Do not "improve" logic, rename functions, or reformat while moving.
- **Python:** `requires-python = ">=3.11,<3.13"` (already in pyproject — do not change).
- **Every task ends green:** `uv run pytest` passes before the task's final commit. Run it; paste failures rather than committing red.
- **Vendored code:** `vendor/claude_video/` stays at repo root, pinned at upstream `755c157`. Never edit files under `vendor/`.
- **Errors:** helpers raise `RuntimeError` (never `SystemExit`); CLI `main()` functions return non-zero ints.
- **Import mapping table** (old flat name → new module path). Use EXACTLY these paths everywhere:

| Old | New |
|---|---|
| `manifest` | `yt_distill.core.manifest` |
| `citation` | `yt_distill.core.citation` |
| `reconcile` | `yt_distill.core.reconcile` |
| `payload` | `yt_distill.core.payload` |
| `enrichment` | `yt_distill.core.enrichment` |
| `video_profile` | `yt_distill.core.video_profile` |
| `models` | `yt_distill.core.models` |
| `env_bootstrap` | `yt_distill.core.env_bootstrap` |
| `dns_fallback` | `yt_distill.core.dns_fallback` |
| `transcript` | `yt_distill.stages.transcript` |
| `frame_ocr` | `yt_distill.stages.frame_ocr` |
| `frame_select` | `yt_distill.stages.frame_select` |
| `reference_follower` | `yt_distill.stages.references` |
| `enrich` | `yt_distill.stages.visual` |
| `extract` | `yt_distill.pipeline.extract` |
| `distill` | `yt_distill.pipeline.distill` |
| `review_loop` | `yt_distill.pipeline.review` |
| `run` | `yt_distill.pipeline.run` |
| `distill_render` | `yt_distill.output.render` |
| `skill_bundle` | `yt_distill.output.skill_bundle` |
| `clean` | `yt_distill.clean` |

- `from vendor.claude_video.scripts import ...` imports stay EXACTLY as they are (vendor ships as a second top-level package, Task 1).
- Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Packaging skeleton (src layout + vendor as package)

**Files:**
- Modify: `pyproject.toml`
- Create: `src/yt_distill/__init__.py`, `src/yt_distill/core/__init__.py`, `src/yt_distill/stages/__init__.py`, `src/yt_distill/pipeline/__init__.py`, `src/yt_distill/output/__init__.py`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Produces: importable `yt_distill` package (empty subpackages) and importable `vendor.claude_video` after `uv sync`. All later tasks rely on this.

- [x] **Step 1: Write the failing test**

Create `tests/test_packaging.py`:

```python
"""The project installs as a src-layout package; vendor stays importable."""
import importlib


def test_yt_distill_package_importable():
    for mod in (
        "yt_distill",
        "yt_distill.core",
        "yt_distill.stages",
        "yt_distill.pipeline",
        "yt_distill.output",
    ):
        importlib.import_module(mod)


def test_vendor_still_importable():
    importlib.import_module("vendor.claude_video.scripts")
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_packaging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'yt_distill'`

- [x] **Step 3: Add build system, scripts stub, and package dirs**

Append to `pyproject.toml` (keep every existing section untouched):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/yt_distill", "vendor"]
```

Create the five `__init__.py` files, each containing only a docstring, e.g. `src/yt_distill/__init__.py`:

```python
"""yt-distill: distill YouTube/local videos into citation-grounded artifacts."""
```

- [x] **Step 4: Sync and run tests**

Run: `uv sync` then `uv run pytest tests/test_packaging.py -v`
Expected: both tests PASS (uv installs the project editable once a build system exists).
Then run the full suite: `uv run pytest` — expected PASS (nothing moved yet).

- [x] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/test_packaging.py
git commit -m "build: src-layout packaging skeleton, vendor as second package"
```

---

### Task 2: Move core modules

**Files:**
- Move (use `git mv`, then fix imports inside the moved files):
  `manifest.py → src/yt_distill/core/manifest.py`,
  `citation.py → src/yt_distill/core/citation.py`,
  `reconcile.py → src/yt_distill/core/reconcile.py`,
  `payload.py → src/yt_distill/core/payload.py`,
  `enrichment.py → src/yt_distill/core/enrichment.py`,
  `video_profile.py → src/yt_distill/core/video_profile.py`,
  `models.py → src/yt_distill/core/models.py`,
  `env_bootstrap.py → src/yt_distill/core/env_bootstrap.py`,
  `dns_fallback.py → src/yt_distill/core/dns_fallback.py`
- Modify: every remaining root `.py` file and every file under `tests/` that imports any of the nine moved names — rewrite per the Global Constraints mapping table.

**Interfaces:**
- Produces: `yt_distill.core.*` modules with UNCHANGED public names (e.g. `yt_distill.core.manifest.Manifest`, `yt_distill.core.models.resolve/doctor/Profile`). Later tasks import these paths.

**CRITICAL — path-derived config:** After moving, grep each moved file for `__file__`. Modules that locate repo-root resources (`models.yaml`, `.env`, `styles/`, `prompts/`) via `Path(__file__).parent` now live two directories deeper. For each such site, replace the repo-root derivation with:

```python
REPO_ROOT = Path(__file__).resolve().parents[3]  # src/yt_distill/core/x.py -> repo root
```

...but ONLY where the old code resolved to the repo root. Verify each case by reading the surrounding code; do not blanket-replace.

- [x] **Step 1: Move the nine files**

```bash
git mv manifest.py citation.py reconcile.py payload.py enrichment.py video_profile.py models.py env_bootstrap.py dns_fallback.py src/yt_distill/core/
```

- [x] **Step 2: Rewrite imports mechanically**

For each of the nine names, update all importers (root scripts, `tests/`, and the moved files importing each other):

```bash
grep -rln "^from \(manifest\|citation\|reconcile\|payload\|enrichment\|video_profile\|models\|env_bootstrap\|dns_fallback\) import\|^import \(manifest\|citation\|reconcile\|payload\|enrichment\|video_profile\|models\|env_bootstrap\|dns_fallback\)\b" --include="*.py" .
```

Rewrite `from manifest import X` → `from yt_distill.core.manifest import X`, `import models` → `from yt_distill.core import models` (adjusting attribute references if any). Also handle `monkeypatch`/`patch` string targets in tests, e.g. `"extract.fetch_transcript"` stays (extract not moved yet) but `"models.doctor"` → `"yt_distill.core.models.doctor"`.

- [x] **Step 3: Fix `__file__`-derived paths**

```bash
grep -n "__file__" src/yt_distill/core/*.py
```

Apply the `parents[3]` fix described above wherever the old code meant repo root (`models.py` locating `models.yaml`, `env_bootstrap.py` locating `.env` are the expected cases — read and confirm).

- [x] **Step 4: Run full suite**

Run: `uv run pytest`
Expected: PASS. If a test fails on a patch-target string, fix the string per the mapping table.

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move core modules into yt_distill.core"
```

---

### Task 3: Move stage modules

**Files:**
- Move: `transcript.py → src/yt_distill/stages/transcript.py`,
  `frame_ocr.py → src/yt_distill/stages/frame_ocr.py`,
  `frame_select.py → src/yt_distill/stages/frame_select.py`,
  `reference_follower.py → src/yt_distill/stages/references.py`,
  `enrich.py → src/yt_distill/stages/visual.py`
- Modify: all importers (root scripts, tests) per the mapping table; patch-target strings in tests (e.g. `"transcript._fetch_via_ytdlp"` → `"yt_distill.stages.transcript._fetch_via_ytdlp"`).

**Interfaces:**
- Consumes: `yt_distill.core.*` (Task 2).
- Produces: `yt_distill.stages.transcript.fetch_transcript`, `yt_distill.stages.frame_ocr.{FrameRecord, FrameClass, read_ocr_json}`, `yt_distill.stages.frame_select.{detect_scene_changes, select_frames, write_selected_frames_json, Selected}`, `yt_distill.stages.references.main`, `yt_distill.stages.visual.{enrich, main}` — all names unchanged, only paths.

- [x] **Step 1: Move the five files**

```bash
git mv transcript.py src/yt_distill/stages/transcript.py
git mv frame_ocr.py src/yt_distill/stages/frame_ocr.py
git mv frame_select.py src/yt_distill/stages/frame_select.py
git mv reference_follower.py src/yt_distill/stages/references.py
git mv enrich.py src/yt_distill/stages/visual.py
```

- [x] **Step 2: Rewrite imports and patch targets**

Same mechanical procedure as Task 2, for names `transcript`, `frame_ocr`, `frame_select`, `reference_follower` (→ `references`), `enrich` (→ `visual`). `from vendor.claude_video.scripts import ...` lines inside the moved files stay untouched. Check the moved files for `__file__`-derived repo-root paths and apply the `parents[3]` fix where needed (`visual.py` may locate `styles/`; verify by reading).

- [x] **Step 3: Run full suite**

Run: `uv run pytest`
Expected: PASS.

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move stage modules into yt_distill.stages"
```

---

### Task 4: Stage registry (new code, TDD)

**Files:**
- Create: `src/yt_distill/stages/registry.py`
- Test: `tests/test_stage_registry.py`

**Interfaces:**
- Produces (later tasks and sub-project 3 rely on these exact names):
  - `CostTier` (IntEnum): `FREE=0, LOCAL_COMPUTE=1, CHEAP_LLM=2, VISION_LLM=3`
  - `Stage` (frozen dataclass): `name: str, cost_tier: CostTier, requires: frozenset[str], produces: frozenset[str], run: Callable[[StageContext], StageResult]`
  - `StageContext` (dataclass): `title_dir: Path, options: dict`
  - `StageResult` (dataclass): `produced: dict[str, Path], diagnostics: list[str]`
  - `register(stage) -> Stage` (raises `RuntimeError` on duplicate name), `get(name) -> Stage` (raises `RuntimeError` if unknown), `all_stages() -> list[Stage]`, `runnable(available: set[str], max_tier: CostTier = CostTier.VISION_LLM) -> list[Stage]`, `clear()` (test helper)

- [x] **Step 1: Write the failing tests**

Create `tests/test_stage_registry.py`:

```python
"""Stage registry: registration, lookup, economical-first ordering."""
from pathlib import Path

import pytest

from yt_distill.stages import registry
from yt_distill.stages.registry import CostTier, Stage, StageContext, StageResult


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    yield
    registry.clear()


def _mk(name, tier, requires=(), produces=()):
    return Stage(
        name=name,
        cost_tier=tier,
        requires=frozenset(requires),
        produces=frozenset(produces),
        run=lambda ctx: StageResult(produced={}, diagnostics=[]),
    )


def test_register_and_get_roundtrip():
    s = registry.register(_mk("ocr", CostTier.LOCAL_COMPUTE))
    assert registry.get("ocr") is s


def test_duplicate_name_raises_runtime_error():
    registry.register(_mk("ocr", CostTier.LOCAL_COMPUTE))
    with pytest.raises(RuntimeError, match="ocr"):
        registry.register(_mk("ocr", CostTier.FREE))


def test_unknown_name_raises_runtime_error():
    with pytest.raises(RuntimeError, match="nope"):
        registry.get("nope")


def test_runnable_orders_by_cost_tier_then_name():
    registry.register(_mk("vision_pass", CostTier.VISION_LLM, requires=["video"]))
    registry.register(_mk("captions", CostTier.FREE, requires=["video"]))
    registry.register(_mk("b_local", CostTier.LOCAL_COMPUTE, requires=["video"]))
    registry.register(_mk("a_local", CostTier.LOCAL_COMPUTE, requires=["video"]))
    names = [s.name for s in registry.runnable({"video"})]
    assert names == ["captions", "a_local", "b_local", "vision_pass"]


def test_runnable_excludes_unmet_requirements():
    registry.register(_mk("needs_transcript", CostTier.FREE, requires=["transcript"]))
    assert registry.runnable({"video"}) == []


def test_runnable_respects_max_tier():
    registry.register(_mk("captions", CostTier.FREE, requires=["video"]))
    registry.register(_mk("vision_pass", CostTier.VISION_LLM, requires=["video"]))
    names = [s.name for s in registry.runnable({"video"}, max_tier=CostTier.CHEAP_LLM)]
    assert names == ["captions"]


def test_stage_run_receives_context():
    seen = {}

    def run(ctx: StageContext) -> StageResult:
        seen["dir"] = ctx.title_dir
        return StageResult(produced={"out": ctx.title_dir / "out.json"}, diagnostics=["ok"])

    registry.register(Stage("probe", CostTier.FREE, frozenset(), frozenset({"out"}), run))
    result = registry.get("probe").run(StageContext(title_dir=Path("/tmp/x"), options={}))
    assert seen["dir"] == Path("/tmp/x")
    assert result.diagnostics == ["ok"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stage_registry.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` on `yt_distill.stages.registry`

- [x] **Step 3: Implement the registry**

Create `src/yt_distill/stages/registry.py`:

```python
"""Stage registry — the modular core of the pipeline.

A *stage* is one processing/enrichment capability. Stages declare what
artifacts they need (`requires`), what they write (`produces`), and how
expensive they are (`cost_tier`). `runnable()` returns stages ordered
economical-first, which makes the escalation principle structural: callers
start at FREE and only raise `max_tier` when a cheaper pass left gaps.

Adding a new enrichment tool later = one module registering one Stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Callable


class CostTier(IntEnum):
    FREE = 0            # cached/remote-free data (e.g. caption APIs)
    LOCAL_COMPUTE = 1   # ffmpeg, OCR, perceptual hashing
    CHEAP_LLM = 2       # text-only LLM calls
    VISION_LLM = 3      # multimodal LLM calls


@dataclass
class StageContext:
    title_dir: Path
    options: dict


@dataclass
class StageResult:
    produced: dict[str, Path]
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Stage:
    name: str
    cost_tier: CostTier
    requires: frozenset[str]
    produces: frozenset[str]
    run: Callable[[StageContext], StageResult]


_REGISTRY: dict[str, Stage] = {}


def register(stage: Stage) -> Stage:
    if stage.name in _REGISTRY:
        raise RuntimeError(f"stage already registered: {stage.name}")
    _REGISTRY[stage.name] = stage
    return stage


def get(name: str) -> Stage:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise RuntimeError(f"unknown stage: {name}") from None


def all_stages() -> list[Stage]:
    return sorted(_REGISTRY.values(), key=lambda s: (s.cost_tier, s.name))


def runnable(available: set[str], max_tier: CostTier = CostTier.VISION_LLM) -> list[Stage]:
    """Stages whose requirements are met, cheapest first."""
    return [
        s for s in all_stages()
        if s.cost_tier <= max_tier and s.requires <= available
    ]


def clear() -> None:
    """Test helper: reset the registry."""
    _REGISTRY.clear()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stage_registry.py -v` then `uv run pytest`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add src/yt_distill/stages/registry.py tests/test_stage_registry.py
git commit -m "feat: stage registry with economical-first ordering"
```

---

### Task 5: Move pipeline, output, and clean modules

**Files:**
- Move: `extract.py → src/yt_distill/pipeline/extract.py`,
  `distill.py → src/yt_distill/pipeline/distill.py`,
  `review_loop.py → src/yt_distill/pipeline/review.py`,
  `run.py → src/yt_distill/pipeline/run.py`,
  `distill_render.py → src/yt_distill/output/render.py`,
  `skill_bundle.py → src/yt_distill/output/skill_bundle.py`,
  `clean.py → src/yt_distill/clean.py`
- Modify: all importers and test patch-target strings per the mapping table (e.g. `"extract._probe_source"` → `"yt_distill.pipeline.extract._probe_source"`, `"distill.doctor"` → `"yt_distill.pipeline.distill.doctor"`).

**Interfaces:**
- Consumes: `yt_distill.core.*`, `yt_distill.stages.*`.
- Produces: every moved module keeps a `main(argv=None) -> int` with its argparse UNCHANGED. Task 6's CLI dispatches to exactly these: `yt_distill.pipeline.extract.main`, `yt_distill.pipeline.distill.main`, `yt_distill.pipeline.review.main`, `yt_distill.pipeline.run.main`, `yt_distill.stages.references.main`, `yt_distill.stages.visual.main`, `yt_distill.clean.main`, `yt_distill.core.models.main`.

- [x] **Step 1: Move the seven files**

```bash
git mv extract.py src/yt_distill/pipeline/extract.py
git mv distill.py src/yt_distill/pipeline/distill.py
git mv review_loop.py src/yt_distill/pipeline/review.py
git mv run.py src/yt_distill/pipeline/run.py
git mv distill_render.py src/yt_distill/output/render.py
git mv skill_bundle.py src/yt_distill/output/skill_bundle.py
git mv clean.py src/yt_distill/clean.py
```

- [x] **Step 2: Rewrite imports and patch targets**

Same mechanical procedure as Tasks 2–3 for names `extract`, `distill`, `review_loop` (→ `review`), `run`, `distill_render` (→ `render`), `skill_bundle`, `clean`. `run.py` invokes extract/distill — update its imports to `from yt_distill.pipeline import extract, distill` style. `review_loop.py` may invoke distill similarly. Check moved files for `__file__` repo-root derivations (styles/, prompts/ lookups in `distill.py` are expected — `parents[3]` fix as in Task 2, but pipeline depth is also 3: `src/yt_distill/pipeline/x.py` → `parents[3]` is repo root. Verify per file.). Do NOT change `Generated_Data` resolution logic (env var `YT_GENERATED_DATA_DIR` + cwd-relative default) — it is cwd-based, not `__file__`-based; leave as-is if so, confirm by reading.

- [x] **Step 3: Run full suite**

Run: `uv run pytest`
Expected: PASS. `tests/test_download_transcript_legacy.py` still passes because `download_transcript.py` remains at root until Task 8 — update its imports of `run` to `yt_distill.pipeline.run` so it keeps working this task.

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move pipeline, output, clean into yt_distill package"
```

---

### Task 6: `yt-distill` console script (TDD)

**Files:**
- Create: `src/yt_distill/cli.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: the eight `main(argv)` functions listed in Task 5's Produces block.
- Produces: `yt_distill.cli.main(argv=None) -> int`; console command `yt-distill` with subcommands `extract, refs, distill, review, run, enrich, clean, doctor`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
"""yt-distill dispatcher: routes subcommands to module main(argv) functions."""
import pytest

from yt_distill import cli


def test_no_args_prints_usage_and_exits_nonzero(capsys):
    rc = cli.main([])
    assert rc != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_unknown_command_exits_nonzero(capsys):
    rc = cli.main(["frobnicate"])
    assert rc != 0
    assert "frobnicate" in capsys.readouterr().err


def test_help_lists_all_subcommands(capsys):
    rc = cli.main(["--help"])
    out = capsys.readouterr().out
    assert rc == 0
    for cmd in ("extract", "refs", "distill", "review", "run", "enrich", "clean", "doctor"):
        assert cmd in out


@pytest.mark.parametrize(
    "cmd,target,forwarded",
    [
        ("extract", "yt_distill.pipeline.extract.main", ["x.mp4", "--force"]),
        ("refs", "yt_distill.stages.references.main", ["TitleDir"]),
        ("distill", "yt_distill.pipeline.distill.main", ["TitleDir", "coding_agent"]),
        ("review", "yt_distill.pipeline.review.main", ["TitleDir"]),
        ("run", "yt_distill.pipeline.run.main", ["x.mp4", "auto"]),
        ("enrich", "yt_distill.stages.visual.main", ["TitleDir", "coding_agent"]),
        ("clean", "yt_distill.clean.main", ["--apply"]),
    ],
)
def test_dispatch_forwards_argv_verbatim(cmd, target, forwarded, mocker):
    m = mocker.patch(target, return_value=0)
    rc = cli.main([cmd, *forwarded])
    assert rc == 0
    m.assert_called_once_with(forwarded)


def test_doctor_prepends_subcommand_for_models_main(mocker):
    m = mocker.patch("yt_distill.core.models.main", return_value=0)
    rc = cli.main(["doctor", "--profile", "gemini-3.5-flash"])
    assert rc == 0
    m.assert_called_once_with(["doctor", "--profile", "gemini-3.5-flash"])


def test_none_return_from_module_main_maps_to_zero(mocker):
    mocker.patch("yt_distill.clean.main", return_value=None)
    assert cli.main(["clean"]) == 0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — no module `yt_distill.cli`

- [x] **Step 3: Implement the dispatcher**

Create `src/yt_distill/cli.py`:

```python
"""yt-distill — single console entry point.

Thin dispatcher: each subcommand forwards argv verbatim to the owning
module's existing `main(argv)` so every historical flag keeps working.
"""
from __future__ import annotations

import importlib
import sys

# subcommand -> (module, attr, argv prefix to prepend)
_COMMANDS: dict[str, tuple[str, str, list[str]]] = {
    "extract": ("yt_distill.pipeline.extract", "main", []),
    "refs": ("yt_distill.stages.references", "main", []),
    "distill": ("yt_distill.pipeline.distill", "main", []),
    "review": ("yt_distill.pipeline.review", "main", []),
    "run": ("yt_distill.pipeline.run", "main", []),
    "enrich": ("yt_distill.stages.visual", "main", []),
    "clean": ("yt_distill.clean", "main", []),
    "doctor": ("yt_distill.core.models", "main", ["doctor"]),
}

_USAGE = (
    "usage: yt-distill <command> [args]\n\n"
    "commands:\n"
    + "\n".join(f"  {name}" for name in _COMMANDS)
    + "\n\nRun `yt-distill <command> --help` for command-specific flags.\n"
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE, end="")
        return 0
    if not argv:
        print(_USAGE, end="", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    entry = _COMMANDS.get(cmd)
    if entry is None:
        print(f"yt-distill: unknown command: {cmd}\n\n{_USAGE}", end="", file=sys.stderr)
        return 2
    module_name, attr, prefix = entry
    module = importlib.import_module(module_name)
    rc = getattr(module, attr)(prefix + rest)
    return 0 if rc is None else int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
```

NOTE on patching: `test_dispatch_forwards_argv_verbatim` patches e.g. `yt_distill.pipeline.extract.main`; because the dispatcher resolves via `importlib.import_module(...)` + `getattr` at call time, the patch is seen. Do not switch to `from x import main` — that would break patching and eager-import heavy deps.

Add to `pyproject.toml`:

```toml
[project.scripts]
yt-distill = "yt_distill.cli:main"
```

- [x] **Step 4: Run tests and verify the console script exists**

Run: `uv sync` then `uv run pytest tests/test_cli.py -v` — expected PASS.
Run: `uv run yt-distill --help` — expected: usage text listing all 8 subcommands, exit 0.
Run: `uv run pytest` — full suite PASS.

- [x] **Step 5: Commit**

```bash
git add src/yt_distill/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: single yt-distill console script dispatching all subcommands"
```

---

### Task 7: Gemini 3.5 Flash profile + optional reasoning effort

**Files:**
- Modify: `models.yaml`
- Modify: `src/yt_distill/core/models.py` (additive `reasoning_effort` field on `Profile`)
- Test: `tests/test_models.py` (append tests)

**Interfaces:**
- Consumes: `yt_distill.core.models.{resolve, Profile}` (existing).
- Produces: `Profile.reasoning_effort: str | None` (default `None`); default profile `gemini-3.5-flash`.

**Background (verified 2026-07-16 on the OpenRouter model card):** `google/gemini-3.5-flash` — 1,048,576-token context, 65,536 max output; text/image/video/audio/PDF input; thinking effort levels minimal/low/medium/high (default medium) via OpenRouter's `reasoning` parameter; $1.50/M input, $9/M output.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_models.py` (read the file first and match its existing fixture/helper style for loading profiles — reuse its helpers rather than inventing new ones):

```python
def test_default_profile_is_gemini_35_flash():
    prof = resolve(None)  # adapt call to this file's existing resolve() usage
    assert prof.model == "google/gemini-3.5-flash"
    assert prof.vision is True
    assert prof.api_key_env == "OPENROUTER_API_KEY"


def test_reasoning_effort_defaults_to_none():
    prof = resolve("gemini-3-flash")
    assert prof.reasoning_effort is None


def test_reasoning_effort_parsed_when_present():
    prof = resolve("gemini-3.5-flash-high")
    assert prof.reasoning_effort == "high"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: new tests FAIL (unknown profile / missing attribute).

- [x] **Step 3: Update models.yaml and Profile**

In `models.yaml`, change `default:` and add two profiles (keep every existing profile untouched):

```yaml
default: gemini-3.5-flash

profiles:
  gemini-3.5-flash:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3.5-flash
    vision: true
    reasoning: true
    api_key_env: OPENROUTER_API_KEY
    max_images: 32
    max_image_bytes: 5242880

  gemini-3.5-flash-high:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-3.5-flash
    vision: true
    reasoning: true
    reasoning_effort: high
    api_key_env: OPENROUTER_API_KEY
    max_images: 32
    max_image_bytes: 5242880
```

In `src/yt_distill/core/models.py`, add to the `Profile` dataclass (match existing field style):

```python
reasoning_effort: str | None = None  # minimal|low|medium|high; None = model default
```

and thread it through the YAML→Profile construction (one line where other optional fields are read). Do NOT wire it into the LLM request in this task — request-side use is sub-project 2/3; this task only makes the field resolvable.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_models.py -v` then `uv run pytest`
Expected: PASS. Also run `uv run yt-distill doctor --profile gemini-3.5-flash` — it may report a failed live probe without an API key; acceptable outcome is a clean structured failure, not a traceback.

- [x] **Step 5: Commit**

```bash
git add models.yaml src/yt_distill/core/models.py tests/test_models.py
git commit -m "feat(models): gemini-3.5-flash default profile + reasoning_effort field"
```

---

### Task 8: Delete superseded legacy files

**Files:**
- Delete: `main.py`, `test_models.py` (repo ROOT only — NOT `tests/test_models.py`), `download_transcript.py`, `transform_transcript.py`, `tests/test_download_transcript_legacy.py`
- Modify: `scripts/dod_check.sh` (remove the "legacy download_transcript.py" section only — the rest of the file is updated in Task 9)

**Interfaces:**
- Consumes: nothing. Produces: nothing — pure removal.

**Supersession evidence (why this loses zero functionality):** `main.py` is the `uv init` hello-world stub; root `test_models.py` duplicates coverage now living in `tests/`; `download_transcript.py` is a forwarding wrapper around `run.py`; `transform_transcript.py` (transcript+style→LLM rewrite) is fully covered by `yt-distill distill`, which adds citations, frames, OCR, and validation.

- [x] **Step 1: Verify nothing imports the doomed files**

```bash
grep -rn "download_transcript\|transform_transcript\|^import main\|from main import" --include="*.py" src/ tests/ scripts/
```

Expected: no hits outside the files being deleted. If there are hits, STOP and report them instead of deleting.

- [x] **Step 2: Delete**

```bash
git rm main.py test_models.py download_transcript.py transform_transcript.py tests/test_download_transcript_legacy.py
```

Then edit `scripts/dod_check.sh`: delete the entire `=== DoD: legacy download_transcript.py ===` block (from that `echo` line to the end of its soft-check commands).

- [x] **Step 3: Run full suite**

Run: `uv run pytest`
Expected: PASS, with the legacy test file simply gone from collection.

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove superseded legacy scripts (see spec for supersession table)"
```

---

### Task 9: Update docs, DoD script, Archon workflow, cursor skills to the new CLI

**Files:**
- Modify: `scripts/dod_check.sh`, `README.md`, `CLAUDE.md`, `.archon/workflows/lesson-liberation.yaml`, every file under `.cursor/skills/` that invokes the old CLI, `scripts/regen_golden_payloads.py` (if it imports flat module names — check).

**Interfaces:**
- Consumes: `yt-distill` CLI (Task 6). Produces: consistent documentation; later verification (Task 10) runs the updated `dod_check.sh`.

**Command translation table** (apply everywhere; flags unchanged):

| Old | New |
|---|---|
| `uv run python extract.py ...` | `uv run yt-distill extract ...` |
| `uv run python reference_follower.py ...` | `uv run yt-distill refs ...` |
| `uv run python distill.py ...` | `uv run yt-distill distill ...` |
| `uv run python review_loop.py ...` | `uv run yt-distill review ...` |
| `uv run python run.py ...` | `uv run yt-distill run ...` |
| `uv run python clean.py ...` | `uv run yt-distill clean ...` |
| `uv run python models.py doctor ...` | `uv run yt-distill doctor ...` |
| (undocumented) `uv run python enrich.py ...` | `uv run yt-distill enrich ...` |

- [x] **Step 1: Update `scripts/dod_check.sh`**

Replace old invocations per the table. The distill dry-run block monkey-patches by module path — update it to:

```bash
YT_GENERATED_DATA_DIR=$TMP uv run python -c "
import sys
from yt_distill.pipeline import distill
distill.doctor = lambda *a, **k: type('R', (), {'ok': True, 'failure_reason': ''})()
sys.exit(distill.main(['test_video', 'knowledge_base', '--dry-run-payload']))
"
```

- [x] **Step 2: Update `scripts/regen_golden_payloads.py`**

Check its imports; rewrite any flat module names per the Global Constraints mapping table. Run it against nothing yet — just confirm `uv run python scripts/regen_golden_payloads.py --help` (or a plain import) doesn't traceback.

- [x] **Step 3: Update README.md and CLAUDE.md**

Apply the command table to every code block. In CLAUDE.md also update: the Entry points table (paths now `src/yt_distill/...`; remove deleted legacy rows; add `cli.py` and `stages/registry.py` rows), the Library modules table paths, and the file-reference conventions (e.g. `extract.py:_probe_source` → `yt_distill/pipeline/extract.py:_probe_source`).

- [x] **Step 4: Update `.archon/workflows/lesson-liberation.yaml` and `.cursor/skills/*`**

```bash
grep -rn "extract.py\|distill.py\|run.py\|review_loop.py\|reference_follower.py\|clean.py\|models.py\|enrich.py" .archon/ .cursor/ README.md CLAUDE.md
```

Apply the command table to every hit. After editing, re-run the grep — expected: zero remaining old-style invocations (mentions of module *paths* in prose are fine if they point at the new `src/yt_distill/` locations).

- [x] **Step 5: Run the DoD gate and commit**

Run: `uv run pytest` then `bash scripts/dod_check.sh`
Expected: both PASS end-to-end.

```bash
git add -A
git commit -m "docs: migrate all docs, workflows, and DoD gate to yt-distill CLI"
```

---

### Task 10: Full verification gate (orchestrator-run, not delegated)

**Files:** none created; verification only. The ORCHESTRATOR runs this task directly.

- [x] **Step 1: Full test suite** — `uv run pytest` → PASS; `uv run pytest -m integration` → PASS (needs real ffmpeg/OCR; run locally).
- [x] **Step 2: DoD gate** — `bash scripts/dod_check.sh` → PASS.
- [x] **Step 3: Golden payload byte-compare** — `uv run python scripts/regen_golden_payloads.py` then `git status --porcelain tests/fixtures` → EMPTY output (payload pipeline byte-identical pre/post restructure). If dirty, investigate before proceeding — do not commit regenerated goldens as a "fix".
- [x] **Step 4: Live smoke run** — `uv run yt-distill run tests/fixtures/test_video.mp4 knowledge_base` (or a short real URL) → exits 0, markdown + `distill_result.json` produced, zero unresolved citations in the banner.
- [x] **Step 5: Root directory check** — `ls *.py` → expected: no Python files left at repo root.
- [x] **Step 6: Final commit if any stragglers, then report** — summarize gate results honestly, including anything skipped.

---

## Orchestration protocol (how Claude runs this plan with Codex workers)

1. **One Codex dispatch per task (Tasks 1–9), sequential.** Each dispatch prompt = the Global Constraints section + that single task's full text, verbatim. Tasks are self-contained by design; do not send the whole plan.
2. **Between tasks the orchestrator reviews:** `git diff HEAD~1` for scope creep (relocation-not-rewrite rule), test output pasted by the worker re-run locally (`uv run pytest`) — trust but verify.
3. **Task 10 is orchestrator-run** — the final gate is not delegated.
4. **Failure handling:** if a worker reports a blocker (e.g. Task 8 Step 1 finds an unexpected importer), the orchestrator resolves it (possibly amending the plan) before re-dispatch; workers never improvise around STOP conditions.
5. **Checkboxes in this file are the progress ledger** — the orchestrator ticks them as tasks land.
