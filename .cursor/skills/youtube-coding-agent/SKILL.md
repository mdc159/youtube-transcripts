---
name: youtube-coding-agent
description: Convert developer tutorial videos into citation-grounded implementation guidance for coding agents. Use for videos with code, commands, APIs, repositories, terminals, IDEs, packages, or software architecture walkthroughs.
---

# YouTube Coding Agent

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run yt-distill extract "<source>"`.
2. Distill with `uv run yt-distill distill <title-dir> coding_agent`.
3. Preserve exact commands, file paths, package names, APIs, and code snippets from transcript or OCR.
4. Mark inferred commands with `# inferred`; do not fabricate flags, paths, versions, or setup steps.
5. Prefer code-frame OCR and code clusters when extracting snippets, but use selected frame images when UI context, indentation, terminal output, or filenames matter.

## Output Contract

Produce implementation guidance with:

- Overview: what the video teaches and who it is for.
- Source & Environment: source repo URL first if one exists (recreation starts from cloning it), plus stated runtime/tool versions.
- Prerequisites: tools, versions, accounts, repo setup, and assumed knowledge.
- Key Concepts: all technical concepts in the speaker's terminology.
- Steps: imperative actions, exact commands, expected results, and caveats.
- Definition of Done: verifiable criteria for what the finished artifact demonstrably does.
- Troubleshooting: only issues mentioned or visibly demonstrated.
- Technical Reference: tools, commands, project structure / visible file trees, APIs, and code snippets.
- Key Takeaways and Resources.
- Open Questions: gaps an agent would hit when recreating ("None identified" if complete).

## Quality Rules

- Every technical claim needs a citation: `seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, or `t=MM:SS`.
- A referenced source repo outranks reconstructed steps as the recreation starting point.
- Extract all tools, commands, file paths, and technical terms.
- Remove filler and promotion while preserving substantive caveats.
- When the video is mostly conceptual, frame the steps as implementation principles rather than pretending there was a concrete tutorial.
