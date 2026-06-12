# Coding Agent Style Guide

Transform a YouTube developer tutorial into structured instructions that a coding agent can follow. The goal: an agent that never watched the video can recreate the thing it demonstrates.

## Output Format

### 1. Overview
One paragraph: what this guide teaches, target audience, assumed skill level.

### 2. Source & Environment
- **Source repository**: If the video or its description references a repo, list its URL here FIRST. When a repo exists, recreation starts from cloning it; the Steps below then serve as walkthrough and verification rather than from-scratch construction.
- **Environment**: Language/runtime versions, OS, package manager, and any version numbers stated or visible on screen. Omit items not mentioned; never guess versions.

### 3. Prerequisites
Bulleted list of required tools/knowledge. Include versions if mentioned.

### 4. Key Concepts
Table format for all technical concepts discussed:

| Concept | Definition |
|---------|------------|
| **Name** | Brief explanation (1-2 sentences) |

Include: tool names, APIs, patterns, mental models, architectural ideas. Use the speaker's exact terminology.

### 5. Steps
Numbered steps with:
- **Action**: Specific task in imperative voice
- **Command**: Code block with the exact command (if stated)
- **Expected Result**: What to verify
- **Notes**: Caveats or alternatives (optional)

For conceptual content, frame steps as "Implementation Steps" - how to apply the patterns discussed.

**Important**: Only include commands that were explicitly stated or shown. If you must infer a command's syntax, mark it with `# inferred` in the code block.

### 6. Definition of Done
What the finished artifact demonstrably does, stated as verifiable criteria an agent can check (e.g., "the server responds on port 3000 with the dashboard shown at `t=12:40`"). Derive only from demonstrated or stated outcomes — cite the segment or frame showing each criterion.

### 7. Troubleshooting
Table format:

| Issue | Cause | Solution |
|-------|-------|----------|
| Problem | Why it happens | How to fix |

Only include issues actually mentioned in the video.

### 8. Technical Reference

**Tools/Commands** (table):
| Tool | Description |
|------|-------------|
| `name` | What it does |

**Project Structure**: Any directories, file paths, or visible file tree (e.g., from an editor sidebar frame). Reproduce visible trees as a code block so an agent can scaffold correctly.

**Code Snippets**: Any code shown, exactly as presented.

### 9. Key Takeaways
3-5 bullet points: main insights and actionable recommendations.

### 10. Resources
Links, repos, courses, or materials mentioned. Omit if none. (The source repo, if any, already leads Section 2 — repeat it here only alongside other resources.)

### 11. Open Questions
Gaps an agent would hit when recreating this: missing commands, unstated versions, skipped configuration, unexplained values. Always include this section; write "None identified" if the guide is complete.

---

## Rules

**Content extraction:**
- Extract EVERY tool, command, file path, and technical term mentioned
- Preserve the speaker's exact terminology
- Never use generic placeholders ("Define requirements") - be specific
- Output should capture the full technical depth, not just a summary
- If a source repo is referenced anywhere (speech, screen, description), surface it in Source & Environment — it outranks reconstructed steps as the recreation starting point

**Accuracy:**
- Only include commands that were explicitly stated
- Mark inferred commands with `# inferred`
- Don't fabricate file paths or tool flags not mentioned
- Preserve caveats and warnings the speaker gave

**Formatting:**
- Use tables for concepts, tools, and troubleshooting
- Use code blocks for all commands and paths
- Convert visual references to text descriptions

**Remove:**
- Conversational filler ("welcome back", "as you can see")
- Promotional content (social links, sponsors)
- Repetition and verbal stumbles
