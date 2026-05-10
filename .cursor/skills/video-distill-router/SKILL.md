---
name: video-distill-router
description: Route YouTube or local video processing requests to the best project workflow. Use when a user asks to process, summarize, distill, transcribe, or convert a video and has not explicitly chosen coding_agent, diy_project, or knowledge_base.
---

# Video Distill Router

## Purpose

Choose the right video distillation workflow before spending tokens on a full LLM pass. The engine extracts transcript, OCR, visual classes, and scene evidence; this skill decides which output skill should use those artifacts.

## Workflow

1. If artifacts do not exist, run extraction with `uv run python extract.py "<source>"`.
2. Build or inspect the lightweight profile from transcript text, `ocr.json`, frame classes, code clusters, measurements, commands, materials, and conceptual terms.
3. Select one workflow:
   - `youtube-coding-agent` for developer tutorials, code, commands, APIs, repos, terminals, IDEs, or UI/dev tooling.
   - `youtube-diy-project` for maker, cooking, craft, electronics, woodworking, repair, materials, measurements, safety, tools, or physical build steps.
   - `youtube-knowledge-base` for talks, interviews, architecture overviews, conceptual explanations, strategy, principles, and broad reference notes.
4. If confidence is low or the top two workflows are close, present the recommendation and alternatives before proceeding.
5. Run distillation with the chosen style: `uv run python distill.py <title-dir> <style>`.

## Routing Rules

- Prefer explicit user intent over automatic routing.
- Preserve citations from transcript segments, frames, code clusters, and timestamps.
- For ambiguous coding plus DIY videos, prefer asking because the desired artifact differs sharply.
- For ambiguous conceptual plus coding videos, default to `knowledge_base` only when the code is incidental.

## Evidence Priorities

- Coding: code OCR, terminal commands, package names, file paths, API names, UI states.
- DIY: measurements, quantities, materials, tools, safety warnings, visual step changes.
- Knowledge base: named concepts, patterns, diagrams, slide text, quotes, tradeoffs.
