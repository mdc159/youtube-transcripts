---
title: "The 2-Agent Method: Builder + Verifier Agent System"
source: "https://www.youtube.com/watch?v=EnXKysJNz_8"
video_title: "GPT 5.5 VERIFIED Opus 4.7 — A Pi Coding Agent That REVIEWS Like YOU"
style: coding_agent
date: 2026-05-06
---

## 1. Overview

This guide teaches the **2-agent method**: a multi-agent architecture pairing a primary **builder agent** with a specialized **verifier agent** that observes all work and autonomously validates it upon completion. The verifier runs unprompted on every stop-hook event, breaks the builder's output into atomic claims, validates each claim deterministically and non-deterministically, and can reprompt the builder when rules are violated. The system is designed for senior engineers who are already running agentic coding workflows and want to eliminate the manual review bottleneck at scale. The core goal is to spend tokens to save engineer time by encoding your review process into a second agent.

---

## 2. Prerequisites

- A custom **Pi coding agent** harness (fully owned and controllable — not vanilla Claude Code, Codex, Gemini, or Open Code, because bash-tool restriction requires harness control)
- At least one capable frontier model running as the builder (e.g., Claude Opus 4.7)
- A second model for the verifier (e.g., GPT 5.5, GLM 5.1 — can be cheaper than the builder)
- Unix socket support in the agent harness (for stop-hook event passing)
- A system prompt engineering practice — the verifier's rules live entirely in its system prompt
- Understanding of the `stop` hook lifecycle in your agent harness

---

## 3. Key Concepts

| Concept | Definition |
|---------|------------|
| **Builder Agent** | The primary Pi coding agent that executes prompts against your codebase. Runs Opus 4.7 or equivalent. Takes all user prompts. |
| **Verifier Agent** | A second, specialized agent that activates on every stop-hook event from the builder. Never receives direct user prompts. Validates the builder's work. |
| **Stop Hook** | An event emitted by the Pi agent harness via Unix socket when any builder prompt completes. The verifier listens for this and automatically triggers. |
| **Unix Socket** | The IPC mechanism connecting builder to verifier. The builder emits an event on each stop; the verifier receives it and kicks off a validation pass. |
| **Atomic Claims** | Every prompt result is decomposed into individually provable true/false statements. Example: "Did the agent find all SQLite databases?" is one atomic claim. |
| **Atomic Claim Validation** | The verifier breaks the builder's output into atomic claims and verifies each one independently — combining deterministic checks (file exists, size, format) with non-deterministic checks (visual/semantic correctness). |
| **Review Constraint** | The bottleneck in agentic coding where the engineer's time is consumed by manually reviewing agent output. The verifier directly attacks this constraint. |
| **Bash Policy / Bash Tool Restriction** | A harness-level security setting that limits what commands the verifier's bash tool can run. In the demo, the verifier is restricted to exactly one script — any other bash call is fully blocked. |
| **One Agent, One Prompt, One Purpose** | The principle that focus agents are performant agents. The verifier only validates; it does not build. |
| **Reprompt** | When the verifier finds a rule violation, it sends a new prompt directly into the builder agent — without engineer involvement. |
| **Positive Feedback Loop / Flywheel** | The verifier reports what it *could not verify* and what it *needs to verify next time*. The engineer encodes this into the verifier's system prompt, improving it with every run. |
| **Session File** | A file maintained by the Pi agent harness that records everything the builder agent has done in a session. The verifier reads this file to have full context of the builder's actions. |
| **Confidence Levels** | The verifier reports confidence in its verification result alongside pass/fail — part of the structured report format. |
| **Templated Engineering** | Encoding your manual review rules directly into the verifier's system prompt so no one-off prompts are possible. Forces discipline by design. |
| **Stacking Verifiers** | Running multiple specialized verifier agents, each focused on one concern (e.g., one for images, one for SQL, one for security). They layer on top of the primary agent independently. |
| **Agentic Engineering** | The discipline of building systems of agents that build and maintain systems, rather than prompting individual agents one-off. Contrasted with vibe coding. |
| **Core Four** | The four levers in an agent harness: Context, Model, Prompt, Tools. When the verifier surfaces a gap, you improve one of these — not fire a one-off prompt. |
| **GLM 5.1** | A cheap, 200k-context model used as the verifier in the SQL demo — spent 2× the tokens the builder did for verification, demonstrating the token-for-time tradeoff. |

---

## 4. Steps

### Implementation Steps — Building the 2-Agent System

**Step 1: Own your agent harness**
- **Action**: Use a Pi coding agent or equivalent harness where you have full control over the system prompt, bash policy, tool list, and stop-hook lifecycle. Do not use vanilla Claude Code, Codex, Gemini, or Open Code for this pattern — they do not expose the required control surfaces.
- **Expected Result**: You can modify the system prompt, restrict the bash tool to specific scripts, and hook into stop events.

**Step 2: Instrument the stop hook**
- **Action**: Configure your builder agent to emit an event on every stop via Unix socket.
- **Command**:
  ```bash
  # On each builder stop, emit to socket (inferred — exact implementation in Pi harness)
  # The builder sends: session_file_path + prompt_context over Unix socket
  ```
- **Expected Result**: The verifier process receives the event every time a builder prompt completes — including when the engineer did not trigger anything manually.

**Step 3: Write the verifier system prompt**
- **Action**: Create a dedicated system prompt for the verifier agent. This is where you encode your entire review process. Include:
  - Rules to check (e.g., "images must not exceed 10 distinct text blocks")
  - How to decompose builder output into atomic claims
  - When to reprompt the builder vs. when to just report
  - The mandatory structured report format (see Step 6)
  - What tools the verifier is allowed to use
- **Notes**: The system prompt is the only way to add rules. There are no one-off prompts. If the verifier misses something, you improve the system prompt — you do not fire a corrective prompt.
- **Example rule added to system prompt**:
  ```
  # Image Verification Rules
  - Max text blocks in any generated image: 10
  - If image exceeds 10 blocks, set status=FAILED and reprompt builder with feedback
  ```

**Step 4: Restrict the bash tool**
- **Action**: In the verifier agent's harness configuration, set a bash policy that allows only one specific script. Block all other bash calls entirely.
- **Expected Result**: If the verifier model tries to call any bash command other than the designated script, the call is fully blocked at the harness level.
- **Notes**: This is critical for security. The bash tool is described as "the most dangerous tool you can give your agents." Restricting it on the verifier is the highest level of control available.

**Step 5: Give the verifier access to the session file**
- **Action**: Configure the verifier to read the builder's session file. The Pi harness maintains this file with a full record of everything the builder has done.
- **Expected Result**: The verifier can inspect every action the builder took during the session without needing the builder to report anything explicitly.

**Step 6: Enforce a structured report format**
- **Action**: Prompt-engineer the verifier's system prompt to always output a report in this structure:
  ```
  Status: SUCCESS | FAILED
  Confidence: <level>
  What did you verify:
    - Atomic claim 1: VERIFIED | FAILED | UNVERIFIED
    - Atomic claim 2: ...
  Total claims: N
  Claims verified: N
  Claims failed: N
  Claims unverified: N
  Feedback given: <text or NONE>
  What could you NOT verify:
    - <item>
  What do you need from me to verify this next time:
    - <item>
  ```
- **Expected Result**: Every verification pass produces a consistent, machine-readable report. The "could not verify" and "need next time" sections drive the flywheel.

**Step 7: Implement reprompt logic**
- **Action**: In the verifier's system prompt, specify that when a rule violation is found, the verifier should construct a feedback prompt and send it to the builder agent.
- **Expected Result**: The verifier autonomously kicks off a new builder prompt — the engineer does nothing. The builder re-executes, the verifier re-validates on the next stop event.

**Step 8: Stack additional verifiers (optional)**
- **Action**: Create additional specialized verifier agents, each with a focused system prompt for one concern (SQL schema, security, image quality, API contracts, etc.). Each runs independently on the same stop-hook event.
- **Notes**: Each verifier is independent of the others and of the primary agent. You can add as many as needed without changing the builder.

**Step 9: Close the flywheel loop**
- **Action**: After each run, read the "What could you NOT verify" and "What do you need from me" sections of the report. Encode any new rules or verification capabilities directly into the verifier's system prompt.
- **Expected Result**: The verifier improves with every prompt cycle. Your review process compounds over time without additional engineer effort per run.

---

## 5. Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Verifier reprompts builder but rule violation persists | Rule in system prompt is ambiguous or model interprets it differently | Rewrite the rule with explicit numeric thresholds (e.g., "max 10 blocks" not "not too many blocks") |
| Verifier can't verify a claim | The claim requires information not in the session file or not accessible to the verifier's tools | Add the claim to "What could you NOT verify" section; encode the verification method into the system prompt on the next iteration |
| Verifier fires a bash call that gets blocked | Verifier model tried to use a command outside its policy | This is expected behavior — the block is the safety mechanism. If the verifier genuinely needs a new command, add it to the allowed script or create a new allowed script. Do not loosen the bash policy. |
| Builder and verifier get out of sync | Stop-hook event lost or Unix socket connection dropped | Check socket connection health; ensure harness restarts the listener on failure |
| Verifier status is always UNVERIFIED for certain claims | The model used for the verifier lacks capability for that modality (e.g., cheap model doing image analysis) | Upgrade the verifier model for that claim type, or split into two verifiers with different models |
| Token spend on verifier is unexpectedly high | Verifier prompt is too broad or context is bloated | Narrow the system prompt; restrict the session file to the most recent N actions |

---

## 6. Technical Reference

**Tools/Models**

| Tool / Model | Role |
|---|---|
| Claude Opus 4.7 | Builder agent — runs user prompts against the codebase |
| GPT 5.5 | Verifier agent in image generation demo — validates visual output and atomic claims |
| GLM 5.1 | Verifier agent in SQL demo — cheap 200k-context model; spent 2× builder tokens on verification |
| GPT Image 2.0 (GPT image 2) | Image generation model called by builder; its output was verified by the verifier |
| Pi coding agent | The custom agent harness used for both builder and verifier |

**File Paths**

```
Pi agent harness:
  verifier agents/          # directory for verifier agent configurations
    <verifier-name>/
      system_prompt.md      # verifier rules + report format
      bash_policy           # allowed bash commands (one script only in demo)

Session file:               # maintained by Pi harness; read by verifier
  <session_file_path>       # full record of all builder actions in session

Output files (image demo):
  arch.jpg                  # architecture diagram generated by builder + GPT Image 2
  arch_clone.jpg            # backup created before verifier triggers re-generation

Verification report:
  <verifier_report_file>    # structured report output per run
```

**Communication Architecture**

```
[Engineer] --> prompt --> [Builder Agent (Opus 4.7)]
                                  |
                            stop hook event
                                  |
                          [Unix Socket]
                                  |
                         [Verifier Agent (GPT 5.5 / GLM 5.1)]
                                  |
                    ┌─────────────┴──────────────┐
                    |                            |
              [Atomic Claim                [Structured Report]
               Validation]                      |
                    |                    [If violation found]
                    |                            |
                    └────────────────> reprompt [Builder Agent]
```

**Verification Report Fields**

| Field | Description |
|-------|-------------|
| `Status` | `SUCCESS` or `FAILED` |
| `Confidence` | Verifier's confidence level in its result |
| `What did you verify` | Numbered atomic claims with VERIFIED / FAILED / UNVERIFIED per claim |
| `Total / Verified / Failed / Unverified` | Claim counts |
| `Feedback given` | Text of reprompt sent to builder, or NONE |
| `What could you NOT verify` | Claims the verifier lacked ability to check — used to improve system prompt |
| `What do you need from me to verify this next time` | Explicit asks for the engineer to encode into system prompt |

---

## 7. Key Takeaways

- **The review constraint is the real bottleneck** — not models, not tools. In agentic coding done properly, you spend time on planning and reviewing. The verifier agent directly attacks the review side by encoding your review rules into an autonomous second agent.
- **Spend tokens to save time** — the verifier spent 5× tokens (image demo) and 2× tokens (SQL demo) vs. the builder. This is the correct tradeoff: token cost is low; engineer time is high.
- **One agent, one prompt, one purpose** — the verifier only verifies. It is restricted to one script in bash. Focus makes it performant and safe.
- **The flywheel compounds** — every run surfaces what the verifier could not verify. Every gap you close in the system prompt makes the next run better. You are templating your engineering, not firing one-off prompts.
- **The bash tool is the highest-risk surface** — restrict it at the harness level for any agent that doesn't need full shell access. The verifier in this system is locked to a single allowed script. This is the security baseline to adopt broadly.

---

## 8. Resources

- **Builder / verifier free version**: Author's public GitHub repository (basic version, core ideas intact)
- **Full verifier specialist suite + GPT Image 2 skill**: Tactical Agent Coding + Agentic Horizon courses (members-only)
- **Course**: Tactical Agentic Coding — 8 lessons covering agentic prompt engineering, custom agents, multi-agent orchestration
- **Course**: Agentic Horizon — 6 lessons including the codebase singularity concept; required for the souped-up verifier version
- **Previous video referenced**: Stripe's blueprint system (covered on channel)
- **Upcoming video referenced**: Agentic security — bash tool damage, damage from within trusted systems
