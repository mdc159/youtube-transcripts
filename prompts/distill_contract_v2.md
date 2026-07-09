# Distillation Prompt Contract — v2

You are transforming a video's transcript and visual evidence into a structured
note. You MUST follow these rules without exception:

1. **No unsupported claims.** Every technical statement, step, code snippet, UI
   observation, or diagram interpretation must cite at least one of:
   - a transcript segment ID like `seg#NNN`
   - a frame ID like `frame_NNN_t-MM-SS` (or its short form `frame_NNN`)
   - a code-frame cluster ID like `cluster_id=cN`
   - a bare timestamp range `t=MM:SS` or `t=MM:SS–MM:SS`
   - a pinned repository reference like `repo:path/to/file#L10-L40@SHA`
     (only paths and SHAs listed in the Repo Evidence block below)
   Statements without a citation are forbidden. **This rule is non-negotiable
   and overrides any conflicting instruction in the style guide.**

2. **Evidence authority & conflicts.** When Repo Evidence is provided:
   repository code is authoritative for **exact syntax**; the transcript is
   authoritative for **intent, ordering, and rationale**; OCR'd frames bridge
   the two. Prefer repo-exact code blocks cited `repo:path#Lx-Ly@SHA`. When the
   video and the repo disagree, **flag the conflict explicitly, never resolve it
   silently** — state both sides with their citations (e.g. "video shows X at
   `t=1:34:02`; repo (SHA abc123) has Y; the repo snapshot is newer"). The
   reconciliation notes in the Repo Evidence block list known conflicts; carry
   each relevant one into the note.

3. **Preserve uncertainty.** When OCR text in the transcript is marked
   `~approximate`, propagate the marker into any code block you emit from it.
   When the input announces `transcript_quality: low` or `none`, add a
   `## Quality Note` section noting it.

4. **Section structure is owned by the style guide.** The style guide
   immediately below contains an "Output Format" (or equivalent) block that
   declares the section headings, ordering, and per-section conventions for
   this note. **Use those sections as authoritative.** Do not reorder them,
   merge them, or invent new top-level sections beyond what the style allows.

   If — and only if — the style guide does not declare any sections, fall back
   to the following default skeleton (omit any section that has no content):

   - `## Summary` — 2–4 sentence overview
   - `## Key Points` — bulleted, each with citation(s)
   - `## Steps / Walkthrough` — numbered, each with citation(s)
   - `## Code` — fenced code blocks with language hints, each with citation(s)
   - `## Tools & References` — names of tools, libraries, URLs mentioned
   - `## Visual Evidence Used` — frame IDs you describe, with one-line interpretations
   - `## Open Questions` — anything ambiguous in the input
   - `## Quality Note` — required only when transcript_quality < high or unresolved citations

5. **No hallucinated visual content.** Do not infer text that is in a frame
   but is not in the OCR. When you describe a frame, prefix the description
   with `frame_NNN observation:` so it is clear the claim is grounded in the
   image rather than invented. Likewise, cite only repo paths and line ranges
   that appear in the Repo Evidence block — never invent repo contents.

6. **Output format.** Return a single Markdown document. Do not wrap it in a
   JSON envelope, do not prefix with prose like "Here is your note", and do
   not add a trailing meta-commentary. The renderer will attach Obsidian YAML
   frontmatter; you should not.

End every section's content; do not leave placeholders. If a section the style
allows you to omit has nothing to say, omit it entirely (do not write "N/A").
