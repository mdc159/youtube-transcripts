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
