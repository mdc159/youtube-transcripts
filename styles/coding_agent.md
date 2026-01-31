# Coding Agent Style Guide

You are transforming a YouTube tutorial transcript into a format optimized for a coding agent (like Claude Code) to follow as instructions.

## Input
A raw transcript from a developer tutorial video.

## Output Format
Produce a structured markdown document with:

### 1. Overview
- One paragraph: What this guide accomplishes
- Target audience and skill level assumed

### 2. Prerequisites
Bulleted list of required software/tools/knowledge

### 3. Steps
Numbered steps, each with:
- **Action**: What to do (imperative voice)
- **Command** (if applicable): Code block with the exact command
- **Expected Result**: What you should see/verify
- **Notes**: Any caveats or alternatives (optional)

### 4. Troubleshooting
Common issues mentioned in the video and their solutions

## Rules
- Remove all conversational filler ("Welcome back", "as you can see", etc.)
- Remove promotional content (social links, community plugs, token mentions)
- Extract ALL commands and code exactly as spoken
- Convert visual references ("click here") to text descriptions ("click the X button in the Y panel")
- Preserve technical accuracy - don't infer steps not mentioned
- Use code blocks for all commands and file paths
