---
name: youtube-knowledge-base
description: Convert talks, interviews, conceptual videos, architecture overviews, discussions, and broad tutorials into citation-grounded knowledge base notes for learning and reference.
---

# YouTube Knowledge Base

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run python extract.py "<source>"`.
2. Distill with `uv run python distill.py <title-dir> knowledge_base`.
3. Prioritize transcript structure, slide text, diagrams, named concepts, quotes, patterns, tradeoffs, and referenced resources.
4. Use visual evidence sparingly unless slides, diagrams, or UI screenshots carry information the transcript does not.

## Output Contract

Produce durable reference notes with:

- Summary: topic, thesis, and audience.
- Key Concepts: definitions, context, and relationships.
- Patterns and Practices: named workflows, best practices, anti-patterns, benefits, and tradeoffs.
- Tools and Technologies: every mentioned tool, API, library, framework, or version.
- Quotes and Insights: notable statements worth preserving verbatim.
- Practical Applications: concrete actions, examples, and next steps.
- Related Topics: prerequisites, resources, and follow-up areas.
- Open Questions: unresolved or unsupported points ("None identified" if everything was clear).

## Quality Rules

- Preserve terminology, nuance, caveats, and speaker perspective.
- Name concepts canonically (singular noun phrase, speaker's term) — downstream ingestion converts them into `[[wikilinks]]` and wiki pages, so names must convert mechanically.
- Do not over-compress complex arguments into generic summaries.
- Include all substantive tools and resources, even if briefly mentioned.
- Every technical or conceptual claim needs a citation: `seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, or `t=MM:SS`.
