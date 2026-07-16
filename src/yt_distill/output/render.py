"""Render distill_result.json → Obsidian-ready markdown.

Two render paths:
  * ``render_markdown`` — structured: maps a JSON-shaped result (key_points,
    steps, code_blocks, …) into the canonical generic-distill section list.
  * ``render_passthrough`` — markdown-from-LLM: the contract instructs the
    model to emit markdown directly; this path keeps that markdown verbatim
    so the *style guide's* section structure flows through unmolested. This
    is the active path for the human_tutorial / coding_agent / diy_project /
    knowledge_base styles whose section shapes differ.
"""
from __future__ import annotations

import re


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)


def _first_prose_line(summary: str, *, max_len: int = 240) -> str:
    """Pick the first non-heading, non-blank line and truncate for frontmatter.

    The LLM frequently starts its output with ``## Summary`` (per the contract),
    so the naive ``splitlines()[0]`` produced ``summary: ## Summary`` in the
    frontmatter and a duplicate heading in the body.
    """
    if not summary:
        return ""
    for raw in summary.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        line = line.replace('"', "'")
        if len(line) > max_len:
            line = line[: max_len - 1].rstrip() + "…"
        return line
    return ""


def _strip_leading_summary_heading(summary: str) -> str:
    """Remove a leading ``## Summary`` (any heading level) so the renderer can
    emit its own canonical heading without producing two of them."""
    if not summary:
        return summary
    lines = summary.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^\s{0,3}#{1,6}\s+summary\s*$", lines[0], re.IGNORECASE):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def _frontmatter(data: dict, style_name: str, today_iso: str) -> str:
    cit = data.get("citations") or {}
    q = data.get("quality") or {}
    fm_summary = _first_prose_line(data.get("summary", ""))
    return (
        "---\n"
        "type: tutorial\n"
        "category: development\n"
        "domain:\n"
        "  - youtube-transcript\n"
        f"  - {style_name}\n"
        "source: youtube-transcript-transform\n"
        f"created: {today_iso}\n"
        "status: inbox-triage\n"
        "tags:\n"
        "  - tutorial\n"
        f"  - {style_name}\n"
        "  - transformed-transcript\n"
        f"summary: {fm_summary}\n"
        "enriched_at: \"\"\n"
        f"model_profile: {data.get('model_profile','')}\n"
        f"prompt_contract_version: {data.get('prompt_contract_version','')}\n"
        "citations:\n"
        f"  segments_referenced: {cit.get('segments_referenced', 0)}\n"
        f"  frames_referenced: {cit.get('frames_referenced', 0)}\n"
        f"  unresolved: {cit.get('unresolved', 0)}\n"
        "quality:\n"
        f"  transcript: {q.get('transcript','')}\n"
        f"  ocr: {q.get('ocr','')}\n"
        f"  frame_coverage: {q.get('frame_coverage','')}\n"
        f"  distillation_confidence: {q.get('distillation_confidence','')}\n"
        "---\n\n"
    )


def _cite(cs: list[str]) -> str:
    return f" ({', '.join(cs)})" if cs else ""


def render_passthrough(data: dict, *, style_name: str, today_iso: str) -> str:
    """Emit the model's markdown body verbatim under our frontmatter.

    Use this when the LLM returned a markdown response (the contract's primary
    mode) so the *style guide's* section structure flows through. Citation
    enforcement still happens upstream in `distill.py` via the citation
    validator, so this is purely a presentation layer.
    """
    parts = [_frontmatter(data, style_name, today_iso)]
    if data.get("citations", {}).get("unresolved", 0) > 0:
        parts.append("> ⚠ This note has unresolved citations. Re-run distill.\n\n")
    body = data.get("summary") or ""
    parts.append(body.rstrip() + "\n")
    return "".join(parts)


def render_markdown(data: dict, *, style_name: str, today_iso: str) -> str:
    parts = [_frontmatter(data, style_name, today_iso)]
    if data.get("citations", {}).get("unresolved", 0) > 0:
        parts.append("> ⚠ This note has unresolved citations. Re-run distill.\n\n")
    summary = _strip_leading_summary_heading(data.get("summary") or "")
    if summary:
        parts.append(f"## Summary\n\n{summary}\n\n")
    if data.get("key_points"):
        parts.append("## Key Points\n\n")
        for p in data["key_points"]:
            parts.append(f"- {p['text']}{_cite(p.get('citations', []))}\n")
        parts.append("\n")
    if data.get("steps"):
        parts.append("## Steps / Walkthrough\n\n")
        for s in data["steps"]:
            parts.append(f"{s['order']}. {s['text']}{_cite(s.get('citations', []))}\n")
        parts.append("\n")
    if data.get("code_blocks"):
        parts.append("## Code\n\n")
        for cb in data["code_blocks"]:
            tag = " ~approximate" if cb.get("approximate") else ""
            parts.append(f"```{cb.get('language','')}{tag}\n{cb['code']}\n```\n{_cite(cb.get('citations', []))}\n\n")
    if data.get("tools_mentioned"):
        parts.append("## Tools & References\n\n")
        for t in data["tools_mentioned"]:
            parts.append(f"- **{t['name']}**{_cite(t.get('citations', []))}\n")
        parts.append("\n")
    if data.get("visual_evidence_used"):
        parts.append("## Visual Evidence Used\n\n")
        for v in data["visual_evidence_used"]:
            parts.append(f"- {v['frame_id']} ({v['class']}, {v['selection_reason']}): {v['interpretation']}\n")
        parts.append("\n")
    if data.get("open_questions"):
        parts.append("## Open Questions\n\n")
        for q in data["open_questions"]:
            parts.append(f"- {q}\n")
        parts.append("\n")
    q = data.get("quality") or {}
    needs_quality_note = q.get("transcript") not in ("high",) or data.get("citations", {}).get("unresolved", 0) > 0
    if needs_quality_note:
        parts.append("## Quality Note\n\n")
        parts.append(f"transcript={q.get('transcript')}, ocr={q.get('ocr')}, frame_coverage={q.get('frame_coverage')}.\n")
        if data.get("warnings"):
            for w in data["warnings"]:
                parts.append(f"- {w}\n")
        parts.append("\n")
    return "".join(parts)
