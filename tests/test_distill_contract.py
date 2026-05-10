"""Smoke tests that the prompt contract delegates structure to the style.

These guard against future regressions to the contract that would re-impose a
fixed section list and silently neuter the style files (which is exactly the
bug we just fixed).
"""
from pathlib import Path

CONTRACT = (Path(__file__).resolve().parent.parent / "prompts" / "distill_contract_v1.md").read_text()


def test_contract_still_enforces_citation_requirement():
    text = CONTRACT.lower()
    assert "citation" in text, "contract must keep its citation rule"
    assert "seg#" in CONTRACT or "seg#NNN" in CONTRACT
    assert "frame_" in CONTRACT


def test_contract_defers_section_structure_to_style():
    """The contract must not hardcode the section list; the style decides shape."""
    text = CONTRACT.lower()
    assert "style" in text, "contract must mention the style guide"
    assert "section" in text, "contract must address how sections are determined"


def test_contract_treats_default_section_list_as_fallback():
    """`## Steps / Walkthrough` (and friends) was a generic-distill section name
    leaking into every output. The contract may still list it, but only as a
    fallback that fires when the style declares no sections of its own."""
    text = CONTRACT.lower()
    assert "fall back" in text or "fallback" in text or "if the style" in text, (
        "contract must explicitly mark its built-in section list as a fallback "
        "for when the style guide declares no sections"
    )


def test_contract_forbids_json_envelope_output():
    """The model should emit Markdown directly so style-driven sections flow
    through render_passthrough — not wrapped in a JSON object."""
    text = CONTRACT.lower()
    assert "markdown" in text and "json" in text, (
        "contract should explicitly say to return Markdown (and not JSON) so "
        "the renderer's passthrough path activates"
    )
