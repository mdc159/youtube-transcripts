# Coding Agent Style Guide

Transform a YouTube developer tutorial into structured instructions that a coding agent can follow.

## Output Format

### 1. Overview
One paragraph: what this guide teaches, target audience, assumed skill level.

### 2. Prerequisites
Bulleted list of required tools/knowledge. Include versions if mentioned.

### 3. Key Concepts
Table format for all technical concepts discussed:

| Concept | Definition |
|---------|------------|
| **Name** | Brief explanation (1-2 sentences) |

Include: tool names, APIs, patterns, mental models, architectural ideas. Use the speaker's exact terminology.

### 4. Steps
Numbered steps with:
- **Action**: Specific task in imperative voice
- **Command**: Code block with the exact command (if stated)
- **Expected Result**: What to verify
- **Notes**: Caveats or alternatives (optional)

For conceptual content, frame steps as "Implementation Steps" - how to apply the patterns discussed.

**Important**: Only include commands that were explicitly stated or shown. If you must infer a command's syntax, mark it with `# inferred` in the code block.

### 5. Troubleshooting
Table format:

| Issue | Cause | Solution |
|-------|-------|----------|
| Problem | Why it happens | How to fix |

Only include issues actually mentioned in the video.

### 6. Technical Reference

**Tools/Commands** (table):
| Tool | Description |
|------|-------------|
| `name` | What it does |

**File Paths**: List any directories or file paths mentioned.

**Code Snippets**: Any code shown, exactly as presented.

### 7. Key Takeaways
3-5 bullet points: main insights and actionable recommendations.

### 8. Resources
Links, repos, courses, or materials mentioned. Omit if none.

---

## Rules

**Content extraction:**
- Extract EVERY tool, command, file path, and technical term mentioned
- Preserve the speaker's exact terminology
- Never use generic placeholders ("Define requirements") - be specific
- Output should capture the full technical depth, not just a summary

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
