"""Phase 2.5: post-process a distilled markdown to surface visual evidence.

The contract-driven distill output cites frames and timestamps, but never
embeds the actual images, never deep-links the timestamps, and reduces
information-rich slides to one-line summaries. This module fixes that.

Tier 1 — deterministic, no extra LLM call:
  * 1A `_inline_frame_images`        Embed each cited frame as ![] inline.
  * 1B `_build_visual_gallery`       Contact-sheet appendix of LLM-seen frames.
  * 1C `_yt_deep_link_timestamps`    Convert t=MM:SS into clickable YouTube URLs.
  * 1D `_build_code_appendix`        Verbatim source code from clustered frames.

Tier 2 — one focused LLM call each:
  * 2A `_mermaid_pipeline_from_steps`
  * 2B `_reference_tables_from_slides`
  * 2C `_mindmap_from_concepts`

`enrich(out_dir, style_name=...)` is the public entry point and is idempotent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# 1C: YouTube deep-links
# ---------------------------------------------------------------------------

# Matches `t=MM:SS` or `t=HH:MM:SS`, with optional range using en-dash, em-dash,
# hyphen, or a tilde. Captures the START timestamp only.
_TS_RE = re.compile(
    r"`(t=(\d{1,2}):(\d{2})(?::(\d{2}))?)(?:[\u2013\u2014\-~]\d{1,2}:\d{2}(?::\d{2})?)?`"
)


def _ts_to_seconds(*, h: str | None, m: str, s: str) -> int:
    if h:
        return int(h) * 3600 + int(m) * 60 + int(s)
    return int(m) * 60 + int(s)


def _video_url_with_t(source_url: str, seconds: int) -> str:
    sep = "&" if "?" in source_url else "?"
    return f"{source_url}{sep}t={seconds}s"


def _yt_deep_link_timestamps(md: str, *, source_url: str) -> str:
    r"""Convert ``\`t=MM:SS\``` citations into clickable YouTube links.

    Idempotent: if a citation is already inside a markdown link
    ``[\`t=...\`](...)`` we leave it alone.
    """
    if not source_url:
        return md

    def repl(m: re.Match) -> str:
        full_backticked = m.group(0)
        m_part, s_part = m.group(2), m.group(3)
        # Three groups means MM:SS, four groups means HH:MM:SS — group(4) is the optional seconds.
        if m.group(4):
            secs = _ts_to_seconds(h=m.group(2), m=m.group(3), s=m.group(4))
        else:
            secs = _ts_to_seconds(h=None, m=m_part, s=s_part)
        return f"[{full_backticked}]({_video_url_with_t(source_url, secs)})"

    parts: list[str] = []
    i = 0
    for m in _TS_RE.finditer(md):
        # Skip if already wrapped in a link: look back for `](` ... not great but cheap;
        # check for "[" immediately before the backtick and ")" immediately after.
        before = md[max(0, m.start() - 1) : m.start()]
        # Look ahead for `](` which would indicate this is the link text of an existing link.
        after_close = md[m.end() : m.end() + 2]
        if before == "[" and after_close.startswith("]("):
            continue
        parts.append(md[i : m.start()])
        parts.append(repl(m))
        i = m.end()
    parts.append(md[i:])
    return "".join(parts)


# ---------------------------------------------------------------------------
# 1A: inline frame embedding
# ---------------------------------------------------------------------------

# Captures both `frame_NNN_t-MM-SS` (full) and bare `frame_NNN` references.
_FRAME_FULL_RE = re.compile(r"`?frame_(\d{3})_t-(\d{2})-(\d{2})`?")
_FRAME_SHORT_RE = re.compile(r"`?frame_(\d{3})`?")


def _resolve_frame_file(out_dir: Path, frame_id: str) -> Path | None:
    """Return the on-disk frame path matching a citation, or None."""
    direct = out_dir / "frames" / f"{frame_id}.jpg"
    if direct.is_file():
        return direct
    # Short form: "frame_023" -> glob for frame_023_t-*.jpg
    if "_t-" not in frame_id:
        for cand in (out_dir / "frames").glob(f"{frame_id}_t-*.jpg"):
            return cand
    return None


def _fenced_code_ranges(md: str) -> list[tuple[int, int]]:
    """Return [(start, end), ...] byte ranges of triple-backtick fenced blocks.

    Detects fences at any indentation level so blocks inside list items
    (which CommonMark allows to be indented to match the list item's content
    column) are also captured. This stops inline-frame embedding from
    injecting ``![](...)`` inside a code block.
    """
    ranges: list[tuple[int, int]] = []
    fence_pat = re.compile(r"^[ \t]*```", re.MULTILINE)
    matches = list(fence_pat.finditer(md))
    i = 0
    while i + 1 < len(matches):
        start = matches[i].start()
        end_match = matches[i + 1]
        end = md.find("\n", end_match.end())
        if end == -1:
            end = len(md)
        ranges.append((start, end))
        i += 2
    return ranges


def _inline_frame_images(md: str, *, out_dir: Path) -> str:
    """Embed each cited frame as ``![alt](frames/file.jpg)`` after its first
    citation. Idempotent — already-embedded frames are skipped. Citations
    inside fenced code blocks are skipped (the embed would corrupt the block).
    """
    embedded: set[str] = set()
    # Pre-scan to find existing embeds and skip them.
    for already in re.finditer(r"!\[frame_(\d{3})(?:_t-\d{2}-\d{2})?\]", md):
        embedded.add(already.group(0))

    code_ranges = _fenced_code_ranges(md)

    def _in_code(pos: int) -> bool:
        return any(s <= pos < e for s, e in code_ranges)

    out: list[str] = []
    last = 0
    # Walk all frame citations in document order. Prefer the long form first.
    matches: list[tuple[int, int, str]] = []
    for m in _FRAME_FULL_RE.finditer(md):
        if _in_code(m.start()):
            continue
        fid = f"frame_{m.group(1)}_t-{m.group(2)}-{m.group(3)}"
        matches.append((m.start(), m.end(), fid))
    # Add short-form matches that aren't covered by an overlapping long match.
    long_ranges = [(s, e) for s, e, _ in matches]
    for m in _FRAME_SHORT_RE.finditer(md):
        if _in_code(m.start()):
            continue
        if any(s <= m.start() < e for s, e in long_ranges):
            continue
        fid = f"frame_{m.group(1)}"
        matches.append((m.start(), m.end(), fid))
    matches.sort(key=lambda t: t[0])

    seen_ids: set[str] = set()
    for start, end, fid in matches:
        if fid in seen_ids:
            continue
        # If we've already embedded any reference for this frame_NNN (long or
        # short), skip — embed each frame at most once per document.
        canonical_short = re.match(r"frame_\d{3}", fid).group(0)
        if any(canonical_short in tag for tag in embedded):
            seen_ids.add(fid)
            continue

        path = _resolve_frame_file(out_dir, fid)
        if path is None:
            seen_ids.add(fid)
            continue
        rel = f"frames/{path.name}"
        # Insert the embed at the end of the line that contains this citation.
        line_end = md.find("\n", end)
        if line_end == -1:
            line_end = len(md)
        out.append(md[last:line_end])
        out.append(f"\n\n![{Path(path).stem}]({rel})\n")
        last = line_end
        seen_ids.add(fid)
        embedded.add(f"![{Path(path).stem}]")
    out.append(md[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# 1B: visual evidence gallery
# ---------------------------------------------------------------------------

def _build_visual_gallery(selected: dict, *, interpretations: dict[str, str]) -> str:
    items = selected.get("selected") or []
    if not items:
        return ""
    parts = ["## Visual Evidence Gallery", "", "Frames the model saw while writing this note:", ""]
    for s in items:
        rel = s["path"]
        frame_id = Path(rel).stem
        cls = s.get("frame_class", "")
        reason = s.get("reason", "")
        caption = interpretations.get(frame_id) or interpretations.get(frame_id.split("_t-")[0]) or ""
        meta = f"`{cls}`" + (f", reason: {reason}" if reason else "")
        parts.append(f"### {frame_id}")
        parts.append(f"![{frame_id}]({rel})")
        parts.append(f"_{meta}_" + (f" — {caption}" if caption else ""))
        parts.append("")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# 1D: code-cluster appendix
# ---------------------------------------------------------------------------

def _build_code_appendix(ocr: dict) -> str:
    """Group code-class frames by ``cluster_id`` and emit verbatim OCR text."""
    frames = ocr.get("frames") or []
    code_frames = [f for f in frames if f.get("frame_class") == "code" and f.get("cluster_id")]
    if not code_frames:
        return ""
    by_cluster: dict[str, list[dict]] = {}
    for f in code_frames:
        by_cluster.setdefault(f["cluster_id"], []).append(f)
    parts = [
        "## Source Code (verbatim from frames)",
        "",
        "Captured via OCR from on-screen code; tagged `~approximate` per the citation contract.",
        "",
    ]
    for cluster_id in sorted(by_cluster):
        # Pick the representative: highest OCR confidence, then longest text.
        rep = max(
            by_cluster[cluster_id],
            key=lambda f: (f.get("ocr_confidence", 0.0), len(f.get("ocr_text", ""))),
        )
        rep_id = Path(rep["path"]).stem
        parts.append(f"### `cluster_id={cluster_id}` (representative: `{rep_id}`)")
        parts.append("")
        parts.append("```text ~approximate")
        parts.append(rep.get("ocr_text", "").rstrip())
        parts.append("```")
        parts.append("")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Tier 2: LLM-driven additions (kept thin so they're easy to mock in tests)
# ---------------------------------------------------------------------------

_MERMAID_PIPELINE_PROMPT = """You will be given the "Step-by-Step Instructions"
section of a tutorial. Convert it into a Mermaid `flowchart TD` diagram. Each
step becomes one node labeled with a short imperative phrase (3-6 words).
Connect them sequentially. Output ONLY the fenced mermaid block — no prose
before or after, no explanation, no extra headings.

```mermaid
flowchart TD
    s1[Step 1 short label] --> s2[Step 2 short label]
    ...
```

Steps section:
"""

_REFERENCE_TABLES_PROMPT = """Below is OCR text extracted from slides in a
tutorial video. Many slides contain tabular data: comparison tables, OS
support matrices, command lists, provider lists, configuration grids, etc.

Extract any clearly tabular content into well-formed Markdown tables. Group
related tables under `### ` subheadings. Cite the source frame ID for each
table. Preserve the exact terminology in the OCR. Skip slides that are not
tabular (titles, hero shots, prose). If nothing tabular is present, output
the literal string `NONE`.

OCR text by frame:
"""

_MINDMAP_PROMPT = """You will be given the "Core Concepts" section of a
tutorial. Convert it into a Mermaid `mindmap` diagram. The root is the
tutorial topic (one short phrase you'll infer). Each concept becomes a child
node; sub-bullets become grandchildren. Output ONLY the fenced mermaid block —
no prose before or after.

```mermaid
mindmap
  root((Topic))
    Concept A
      detail
    Concept B
```

Core Concepts section:
"""


def _call_llm(profile, prompt: str) -> str:
    """Single-turn text-only call. Mocked in tests."""
    import os
    from openai import OpenAI

    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"missing API key {profile.api_key_env}")
    client = OpenAI(base_url=profile.base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=profile.model,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    )
    return (resp.choices[0].message.content or "").strip()


def _extract_section(md: str, heading_words: Iterable[str]) -> str | None:
    """Find a top-level section by approximate heading match (case-insensitive).

    Sub-headings deeper than the matched section are kept as part of it; only a
    sibling-or-shallower heading terminates capture.
    """
    lines = md.splitlines()
    in_section = False
    section_depth = 0
    captured: list[str] = []
    target = [w.lower() for w in heading_words]
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m:
            depth = len(m.group(1))
            heading_text = m.group(2).lower()
            if not in_section and any(t in heading_text for t in target):
                in_section = True
                section_depth = depth
                continue
            if in_section and depth <= section_depth:
                break
        if in_section:
            captured.append(line)
    text = "\n".join(captured).strip()
    return text or None


def _mermaid_pipeline_from_steps(md: str, *, profile) -> str:
    section = _extract_section(md, ["step-by-step", "steps"])
    if not section:
        return ""
    raw = _call_llm(profile, _MERMAID_PIPELINE_PROMPT + section)
    if "```mermaid" not in raw:
        return ""
    return raw.strip() + "\n"


def _reference_tables_from_slides(ocr: dict, *, profile, min_chars: int = 200) -> str:
    frames = ocr.get("frames") or []
    dense = [
        f
        for f in frames
        if f.get("frame_class") == "slide_text" and len(f.get("ocr_text", "")) >= min_chars
    ]
    if not dense:
        return ""
    # Cap to avoid blowing the context window.
    dense = dense[:30]
    payload = "\n\n".join(
        f"--- {Path(f['path']).stem} ---\n{f['ocr_text']}" for f in dense
    )
    raw = _call_llm(profile, _REFERENCE_TABLES_PROMPT + payload)
    if not raw or raw.strip().upper().startswith("NONE"):
        return ""
    return f"## Reference Tables\n\n{raw.strip()}\n"


def _mindmap_from_concepts(md: str, *, profile) -> str:
    section = _extract_section(md, ["core concepts", "key concepts"])
    if not section:
        return ""
    raw = _call_llm(profile, _MINDMAP_PROMPT + section)
    if "```mermaid" not in raw:
        return ""
    return raw.strip() + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Marker used to delimit the enrichment block so we can rewrite it idempotently.
_ENRICH_BEGIN = "<!-- enrich:begin -->"
_ENRICH_END = "<!-- enrich:end -->"


def _strip_existing_enrichment(md: str) -> str:
    pat = re.compile(re.escape(_ENRICH_BEGIN) + r".*?" + re.escape(_ENRICH_END) + r"\s*", re.DOTALL)
    return pat.sub("", md).rstrip() + "\n"


def _strip_existing_inline_embeds(md: str) -> str:
    """Remove ``\\n\\n![frame_xxx](frames/...)\\n`` lines that we previously
    inserted, so re-running enrich produces the same output."""
    return re.sub(r"\n\n!\[frame_\d{3}_t-\d{2}-\d{2}\]\(frames/[^)]+\)\n", "", md)


def enrich(
    out_dir: Path,
    *,
    style_name: str,
    profile=None,
    do_mermaid: bool = True,
    do_tables: bool = True,
    do_mindmap: bool = True,
) -> Path:
    """Apply Tier 1 + Tier 2 enrichment to ``<title>_<style>.md`` in place.

    Returns the path that was written. Idempotent: re-running on an
    already-enriched markdown produces equivalent output.
    """
    md_path = out_dir / f"{out_dir.name}_{style_name}.md"
    if not md_path.is_file():
        raise FileNotFoundError(md_path)

    md = md_path.read_text()
    md = _strip_existing_enrichment(md)
    md = _strip_existing_inline_embeds(md)

    # Source URL for deep-links + ocr/selected/interpretations.
    meta_path = out_dir / "extract_meta.json"
    source_url = ""
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        source_url = meta.get("source_url", "") or ""

    ocr_path = out_dir / "ocr.json"
    ocr = json.loads(ocr_path.read_text()) if ocr_path.is_file() else {"frames": []}

    sel_path = out_dir / "selected_frames.json"
    selected = json.loads(sel_path.read_text()) if sel_path.is_file() else {"selected": []}

    # Tier 1A: inline frame embeds (modifies body) before deep-links so
    # backticked frame IDs aren't disturbed by link rewriting.
    md = _inline_frame_images(md, out_dir=out_dir)

    # Tier 1C: deep-link timestamps in the body.
    md = _yt_deep_link_timestamps(md, source_url=source_url)

    # Build the appended sections.
    interpretations = _interpretations_from_md(md)
    appendix_parts: list[str] = []

    # Tier 2A: mermaid pipeline at the top of Step-by-Step section.
    if do_mermaid and profile is not None:
        try:
            mermaid = _mermaid_pipeline_from_steps(md, profile=profile)
        except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
            print(f"[enrich] mermaid pipeline failed: {exc}", file=sys.stderr)
            mermaid = ""
        if mermaid:
            md = _insert_after_heading(md, ["step-by-step", "steps"], mermaid + "\n")

    # Tier 2C: mindmap inside Core Concepts.
    if do_mindmap and profile is not None:
        try:
            mindmap = _mindmap_from_concepts(md, profile=profile)
        except Exception as exc:  # noqa: BLE001
            print(f"[enrich] mindmap failed: {exc}", file=sys.stderr)
            mindmap = ""
        if mindmap:
            md = _insert_after_heading(md, ["core concepts", "key concepts"], mindmap + "\n")

    # Tier 1B: gallery
    gallery = _build_visual_gallery(selected, interpretations=interpretations)
    if gallery:
        appendix_parts.append(gallery)

    # Tier 1D: code appendix
    code_appx = _build_code_appendix(ocr)
    if code_appx:
        appendix_parts.append(code_appx)

    # Tier 2B: reference tables (LLM)
    if do_tables and profile is not None:
        try:
            tables = _reference_tables_from_slides(ocr, profile=profile)
        except Exception as exc:  # noqa: BLE001
            print(f"[enrich] reference tables failed: {exc}", file=sys.stderr)
            tables = ""
        if tables:
            appendix_parts.append(tables)

    if appendix_parts:
        appendix = "\n".join(appendix_parts).strip() + "\n"
        md = md.rstrip() + "\n\n" + _ENRICH_BEGIN + "\n" + appendix + _ENRICH_END + "\n"

    md_path.write_text(md)
    return md_path


def _interpretations_from_md(md: str) -> dict[str, str]:
    """Mine ``frame_NNN observation: ...`` lines from the markdown so the
    gallery can reuse the LLM's own interpretations as captions."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"`?(frame_(\d{3})(?:_t-\d{2}-\d{2})?)`?\s+observation:\s*([^\n]+)",
        md,
    ):
        full_id = m.group(1)
        text = m.group(3).strip().rstrip(".")
        out.setdefault(full_id, text)
        out.setdefault(f"frame_{m.group(2)}", text)
    return out


def _insert_after_heading(md: str, heading_words: Iterable[str], inserted: str) -> str:
    """Insert ``inserted`` just after the first heading line that contains any
    of ``heading_words`` (case-insensitive)."""
    target = [w.lower() for w in heading_words]
    lines = md.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.*?)\s*$", line.rstrip("\n"))
        if m and any(t in m.group(2).lower() for t in target):
            # Skip a single blank line after the heading if present.
            insert_at = idx + 1
            if insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            lines.insert(insert_at, inserted if inserted.endswith("\n") else inserted + "\n")
            return "".join(lines)
    return md


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrich a distilled markdown with visuals + diagrams.")
    p.add_argument("title", help="Title (subdir of Generated_Data/) or absolute path")
    p.add_argument("style", help="Style name (matches the *_<style>.md filename)")
    p.add_argument("--model", default=None, help="Model profile for Tier 2 LLM calls")
    p.add_argument("--no-mermaid", action="store_true", help="Skip the Mermaid pipeline diagram")
    p.add_argument("--no-tables", action="store_true", help="Skip the reference-tables LLM pass")
    p.add_argument("--no-mindmap", action="store_true", help="Skip the Mermaid mindmap")
    p.add_argument("--no-llm", action="store_true", help="Tier 1 only — skip every LLM call")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import os

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    out_dir = (base / args.title).resolve() if not Path(args.title).is_absolute() else Path(args.title)

    profile = None
    if not args.no_llm:
        from yt_distill.core.models import resolve

        repo_root = Path(__file__).resolve().parents[3]
        profile = resolve(cli=args.model, models_yaml=repo_root / "models.yaml")
        print(f"[enrich] profile={profile.name} model={profile.model}")

    md_path = enrich(
        out_dir,
        style_name=args.style,
        profile=profile,
        do_mermaid=not args.no_mermaid and not args.no_llm,
        do_tables=not args.no_tables and not args.no_llm,
        do_mindmap=not args.no_mindmap and not args.no_llm,
    )
    print(f"[enrich] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
