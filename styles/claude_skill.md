# Claude Skill Style Guide

Transform a long-form tutorial into the body of a **self-sufficient skill package**. The reader is a *different* agent, on a *different* machine, with **no access to the video, the transcript, or your memory of this distillation**. Anything not written here does not exist for them. Write so that agent can execute the whole lesson — and repeat any part of it — start to finish without the source.

## Output Format

### 1. When To Use This Skill
One trigger-oriented paragraph: what this skill builds/teaches and the situations in which an agent should reach for it. Written so a router can match tasks to it. (This paragraph becomes the package's frontmatter description — make it self-contained.)

### 2. Prerequisites
Bulleted list of required software, hardware, assets, and prior knowledge — **with versions exactly as stated or shown on screen**. Never guess a version; mark uncertain ones `~approximate`. Include where each item is obtained if the video says.

### 3. Build Manifest
Enumerate **every artifact the instructor constructs** (projects, levels, blueprints, materials, systems, devices — whatever the domain). Table:

| ID | Artifact | Type | Built in | Done when |
|----|----------|------|----------|-----------|
| BM-1 | Name | project/material/blueprint/… | Lesson N steps X–Y | Verifiable completion criterion |

This is the downstream acceptance checklist. Every item must link to the steps that build it, and every lesson step must serve some manifest item.

### 4. Environment Setup
Ordered, imperative steps that take a fresh machine to "ready to start Lesson 1". Exact installer names, project template choices, settings values.

### 5. Lessons
One `####`-titled lesson per coherent chunk of the tutorial, in order. Each lesson contains numbered steps:

- **Action**: imperative, specific ("Set *Final Gather Quality* to **4.0**", never "adjust quality")
- **Where**: exact UI path / panel / menu / file, as shown or stated
- **Values**: exact numbers, names, and settings — the difference between reproducible and useless
- **Expected result**: what the agent should observe
- **Why** (optional, one line): the instructor's stated rationale
- `status: distilled`

Code shown or referenced must appear as fenced blocks. When a cloned source repo is available, prefer repo-exact code and cite `repo:path#Lx-Ly@SHA`; flag any difference from what the video shows — never silently resolve.

### 6. Techniques Learned
The transferable methods an agent should *absorb*, abstracted from this project so they can be reapplied elsewhere. For each: **Name**, **When to apply**, **Method** (the steps in general form), **Source** (citation into the lessons above).

### 7. Gotchas & Conflicts
- Every caveat, warning, and mistake-recovery the instructor demonstrated.
- Every **flagged conflict** between evidence streams (e.g. "video shows X at `t=1:34:02`; repo (SHA abc123) has Y; repo is newer"). State both sides; never resolve silently.

### 8. Open Gaps
Anywhere a consuming agent would be *guessing*: missing values, ambiguous UI locations, undefined terms, referenced-but-absent code or assets. Always include this section; write "None identified" if complete.

---

## Rules

**Self-sufficiency (overriding goal):**
- The consuming agent has ONLY this document and the packaged references. No video, no transcript, no follow-up questions.
- Every step must be executable without guessing. If the exact value/location is unknown, say so in Open Gaps rather than papering over it.
- Preserve exact on-screen values, names, and paths — approximations destroy reproducibility.

**Fidelity:**
- Only include actions actually demonstrated or stated. Mark inferred syntax with `# inferred`.
- Preserve the instructor's exact terminology and their ordering of work.
- Repo code is authoritative for exact syntax; the transcript is authoritative for intent, ordering, and rationale; conflicts get flagged in §7, never resolved silently.
- Every step carries `status: distilled` — never `verified`; verification happens downstream, later, elsewhere.

**Structure:**
- Every Build Manifest item links to its steps; every lesson step serves a manifest item.
- Use tables for the manifest and prerequisites; fenced code blocks for all code, commands, and paths.

**Remove:**
- Conversational filler, sponsor reads, channel promotion, verbal stumbles, repetition.
