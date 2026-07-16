---
name: youtube-claude-skill
description: Distill a long-form tutorial video into a self-sufficient Claude Code skill package that a different agent, on a different machine, with no access to the source, can follow end to end. Use for multi-hour walkthroughs and courses that must be preserved as executable lessons.
---

# YouTube Claude Skill

## Workflow

1. Ensure extraction artifacts exist. If needed, run `uv run yt-distill extract "<source>"`.
2. Harvest linked sources: `uv run yt-distill refs <title-dir>` (clones linked repos pinned to SHA, fetches docs).
3. Distill with `uv run yt-distill distill <title-dir> claude_skill` — writes the standard note pair plus a bundle at `Generated_Data/<title>/skills/<slug>/`.
4. The bundle is the deliverable: `SKILL.md` + `assets/` (cited frames) + `reference/` (repo pointers + snapshots + docs) + `provenance.json`.
5. Write for a consuming agent that has ONLY the bundle — no video, no transcript, no follow-up questions. Anything not in the bundle does not exist for them.

## Output Contract

`SKILL.md` must contain:

- When To Use This Skill: trigger-oriented paragraph (becomes the frontmatter description).
- Prerequisites: software/hardware/assets with versions exactly as stated or shown; `~approximate` when uncertain.
- Build Manifest: every artifact the instructor constructs, each linked to its steps with a verifiable done-when — the downstream acceptance checklist.
- Environment Setup: fresh machine → ready for Lesson 1.
- Lessons: ordered imperative steps with exact Where/Values/Expected result; `status: distilled` on every step (never `verified` — verification happens downstream, elsewhere).
- Techniques Learned: transferable methods abstracted for reuse beyond this project.
- Gotchas & Conflicts: instructor caveats plus flagged evidence conflicts (video vs repo vs OCR) — both sides stated, never silently resolved.
- Open Gaps: anywhere a consuming agent would be guessing ("None identified" if complete).

## Quality Rules

- Repo code is authoritative for exact syntax; transcript for intent, ordering, rationale; OCR bridges them. Conflicts get flagged, never resolved silently.
- Every technical claim carries a citation (`seg#NNN`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, `t=MM:SS`, or `repo:path#Lx-Ly@SHA`).
- Exact on-screen values, names, and UI paths are mandatory when shown — approximations destroy reproducibility.
- Not reachable via `auto` routing — explicit style only.
