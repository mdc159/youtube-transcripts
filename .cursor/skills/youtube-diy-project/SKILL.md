---
name: youtube-diy-project
description: Convert DIY, maker, electronics, woodworking, repair, cooking, craft, or hands-on project videos into citation-grounded build instructions with materials, tools, safety notes, and step evidence.
---

# YouTube DIY Project

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run yt-distill extract "<source>"`.
2. Distill with `uv run yt-distill distill <title-dir> diy_project`.
3. Prioritize visual evidence around scene changes, materials lists, measurements, tools, before/after states, and safety demonstrations.
4. Use transcript citations for spoken instructions and frame citations for visible parts, dimensions, UI readouts, labels, or assembly states.

## Output Contract

Produce build-ready instructions with:

- Project Summary: what is being built and why.
- Project Info: difficulty, time estimate, and cost estimate if mentioned.
- Materials List or Ingredients (bill of materials): exact quantities, dimensions, specs/ratings, brands, part numbers, optional substitutes, and the timestamp where each item is mentioned. No sourcing or purchasing research — only what the video states.
- Tools Required: specific sizes/types and alternatives.
- Theory of Operation: how the finished build works, the role of each major component, and why key values matter (when the video explains or demonstrates it).
- Cautions: PPE, hazards, operational warnings, and mistakes the maker warns against.
- Instructions: numbered steps with exact measurements, tips, and watch-for notes.
- Variations and Resources when mentioned.
- Open Questions: unstated measurements, skipped steps, unspecified materials ("None identified" if complete).

## Quality Rules

- Preserve all measurements, quantities, and specifications exactly.
- Do not include sections that do not apply.
- Convert vague visual references into concrete descriptions using frame evidence.
- Capture warnings about what not to do as watch-for notes.
- Every build-critical claim needs a citation: `seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, or `t=MM:SS`.
