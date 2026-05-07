import pytest
from citation import extract_citations, validate_citations, ResolutionContext


def test_extract_all_citation_forms():
    text = "See seg#42 and frame_017 also frame_017_t-01-23 plus cluster_id=c4 and t=02:30 and t=02:30–02:45."
    cits = extract_citations(text)
    kinds = {c.kind for c in cits}
    assert "segment" in kinds
    assert "frame" in kinds
    assert "cluster" in kinds
    assert "timestamp" in kinds


def test_validate_resolves_real_segments():
    ctx = ResolutionContext(segment_ids={1, 2, 42}, frame_ids={"frame_017_t-01-23"}, cluster_ids={"c4"})
    text = "seg#42 frame_017_t-01-23 cluster_id=c4"
    res = validate_citations(text, ctx)
    assert res.unresolved == []


def test_validate_flags_unresolved():
    ctx = ResolutionContext(segment_ids={1}, frame_ids=set(), cluster_ids=set())
    text = "seg#42 frame_999"
    res = validate_citations(text, ctx)
    assert len(res.unresolved) == 2
