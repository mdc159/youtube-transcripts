---
name: youtube-human-tutorial
description: Convert developer or maker tutorial videos into clear, human-readable, step-by-step guides. Use when the user wants to apply the information from a video to their own project.
---

# YouTube Human Tutorial

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run yt-distill extract "<source>"`.
2. Distill with `uv run yt-distill distill <title-dir> human_tutorial`.
3. Prioritize making the output conversational, clear, and actionable for a human reader.
4. Preserve exact commands, file paths, and code snippets from the transcript or OCR.
5. Translate visual actions (like navigating a UI) into clear text instructions.

## Output Contract

Produce a step-by-step tutorial with:

- Introduction: what the tutorial covers and what will be achieved.
- Prerequisites: tools, software, accounts, and assumed knowledge.
- Core Concepts: brief explanations of the main ideas.
- Step-by-Step Instructions: numbered steps with goals, actions, code/commands, and explanations.
- Tips and Gotchas: common pitfalls and alternative approaches.
- Conclusion: wrap-up and next steps.
- Open Questions: anything glossed over that the reader must figure out ("None identified" if complete).

## Quality Rules

- Write in a conversational, encouraging, and clear tone.
- Address the reader directly (e.g., "First, you'll need to...").
- Ensure all essential code snippets and commands are captured accurately.
- Every technical claim, code block, or major step needs a citation: `seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, or `t=MM:SS`.
- Remove filler words and repetitive phrasing, but preserve the speaker's insights and warnings.
