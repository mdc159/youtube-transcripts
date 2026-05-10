---
name: youtube-diy-project
description: Convert DIY, maker, electronics, woodworking, repair, cooking, craft, or hands-on project videos into citation-grounded build instructions with materials, tools, safety notes, and step evidence.
---

# YouTube DIY Project

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run python extract.py "<source>"`.
2. Distill with `uv run python distill.py <title-dir> diy_project`.
3. Prioritize visual evidence around scene changes, materials lists, measurements, tools, before/after states, and safety demonstrations.
4. Use transcript citations for spoken instructions and frame citations for visible parts, dimensions, UI readouts, labels, or assembly states.

## Output Contract

Produce build-ready instructions with:

- Project Summary: what is being built and why.
- Project Info: difficulty, time estimate, and cost estimate if mentioned.
- Materials List or Ingredients: exact quantities, dimensions, brands, part numbers, and optional substitutes.
- Tools Required: specific sizes/types and alternatives.
- Safety Notes: PPE, hazards, and warnings.
- Instructions: numbered steps with exact measurements, tips, and watch-for notes.
- Variations and Resources when mentioned.

## Quality Rules

- Preserve all measurements, quantities, and specifications exactly.
- Do not include sections that do not apply.
- Convert vague visual references into concrete descriptions using frame evidence.
- Capture warnings about what not to do as watch-for notes.
- Every build-critical claim needs a citation: `seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, or `t=MM:SS`.
