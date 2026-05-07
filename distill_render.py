"""Render distill_result.json → Obsidian-ready markdown."""
from __future__ import annotations

from typing import Any


def _frontmatter(data: dict, style_name: str, today_iso: str) -> str:
    cit = data.get("citations") or {}
    q = data.get("quality") or {}
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
        f"summary: {data.get('summary','').splitlines()[0] if data.get('summary') else ''}\n"
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


def render_markdown(data: dict, *, style_name: str, today_iso: str) -> str:
    parts = [_frontmatter(data, style_name, today_iso)]
    if data.get("citations", {}).get("unresolved", 0) > 0:
        parts.append("> ⚠ This note has unresolved citations. Re-run distill.\n\n")
    if data.get("summary"):
        parts.append(f"## Summary\n\n{data['summary']}\n\n")
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
