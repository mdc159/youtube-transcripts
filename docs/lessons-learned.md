# Lessons Learned — Issues & Solutions Log

Living log of real issues hit during development, how they were diagnosed, and
what we learned. Newest entries appended per section. Started 2026-07-16
during the modular restructure (sub-project 1) and robustness hardening
(sub-project 2).

Format: **Symptom → Root cause → Fix → Lesson.**

---

## Orchestrating Codex workers (Herdr fleet)

### 1. Model id rejected (400)
- **Symptom:** `codex exec -m gpt-5.2-codex` → "model is not supported when using Codex with a ChatGPT account". Same for `gpt-5.6`, `gpt-5.6-codex`.
- **Root cause:** ChatGPT-backed Codex accounts only resolve the model configured in `~/.codex/config.toml` (`gpt-5.6-sol`); skill docs carried stale model tables.
- **Fix:** never pass `-m`; the config default is the wanted model.
- **Lesson:** verify model availability against the live config, not skill/reference tables.

### 2. Codex exec sandbox: five walls, one protocol
- **Symptoms (hit in sequence):** uv cache write denied (os error 183) → repo-local cache still failed: no network (os error 10013) → copy-mode venv fixed reads but `python.exe` trampoline to uv-managed interpreter wouldn't execute → `.git` read-only, no commits → pane scrollback evaporates when the process exits.
- **Root cause:** `codex exec --full-auto` sandbox = workspace-write only, no network, no out-of-workspace exec, protected `.git`.
- **Fix (stable division of labor):** headless workers do FILE EDITS ONLY (Move-Item for renames); orchestrator runs pytest, reviews diff, commits (`git add -A` records renames identically). Read final worker reports from `~/.codex/sessions/**/rollout-*.jsonl` (`task_complete` → `last_agent_message`), not the pane.
- **Lesson:** don't fight a sandbox wall-by-wall; redraw the work split around what the sandbox allows. Also: workers that "died" had actually STOPPED CLEANLY with a report we couldn't see — always find the report channel before diagnosing death.
- **Superseded by:** interactive workers (entry 4) restored worker-run tests.

### 3. Herdr status semantics — `idle` vs `done`
- **Symptom:** waits raced or hung; `herdr agent list` went empty and was misread as "worker died"; a wait for `done` on a visible pane timed out though work finished.
- **Root cause:** `idle` and `done` are the SAME completion state with different visibility (visible tab → `idle`, background → `done`); agents drop off `agent list` when their process exits — that means FINISHED, not died.
- **Fix:** treat either status as completion and let a pane/log READ be the arbiter; watch for commits or artifacts as the true done-signal for headless workers.
- **Lesson:** learn a tool's state model before building watchers on it (the `herdr-fleet` skill documents this — it arrived two days after we derived it the hard way).

### 4. Interactive workers beat headless for this environment
- **Symptom:** headless exec workers couldn't run tests (sandbox), slowing the loop.
- **Fix:** `herdr pane split` → boot `codex` interactive → wait idle → submit via `pane run` → supervise with short wait+read rounds; orchestrator answers `blocked` prompts. Workers now run the suite themselves; orchestrator still re-verifies + commits.
- **Two boot-time gotchas (both predicted by the herdr-fleet skill):** (a) codex self-updated at launch (0.144.4 → 0.144.5) — verify the real prompt UI via `pane read` before submitting; (b) long prompts arrive as bracketed paste and the trailing Enter gets swallowed — text sits unsubmitted; nudge with `herdr pane send-keys <pane> Enter` and confirm status flips to `working`.
- **Lesson:** interactive + supervised > headless + sandboxed when the orchestrator can answer approvals. Read the platform skill FIRST — it encoded both failure modes we'd otherwise rediscover.

### 5. Blanket process-kill nearly hit the user's own session
- **Symptom:** after stopping a stuck background task, orphaned `codex.exe` PIDs were killed wholesale; one belonged to Mike's separate long-running Codex session (it survived by luck).
- **Fix/rule:** never blanket-kill by process name; match the specific session (start time, cwd, session id).
- **Lesson:** on a shared machine, other agents are always running. Identify before you kill.

### 6. Worker edit quality: one indentation break in ~30 files
- **Symptom:** worker rewrote `from models import resolve` inside an `if` block at the wrong indent → IndentationError caught by the suite.
- **Fix:** orchestrator fixed inline; added "preserve indentation exactly" to the standing worker addendum.
- **Lesson:** mechanical-edit workers need the suite run after EVERY batch; the review loop caught this in seconds. Feed each flub back into the briefing template so it can't repeat.

## Test baseline & verification

### 7. "Suite is green" was never true on Windows
- **Symptom:** plan assumed a green baseline; first full run showed 8 failures before any change landed.
- **Root cause:** repo developed on WSL/Linux; Windows-only defects (see 8, 9) were latent.
- **Fix:** stash-and-retest proved the failures pre-existed; gate redefined as "failure set byte-identical to baseline" per task, and the baseline list went into every worker briefing.
- **Lesson:** measure the baseline before promising to preserve it. "No new failures vs. measured baseline" is the honest gate; also tell workers which failures are NOT theirs to chase.

### 8. Golden "drift" was mojibake (and a product bug, not test noise)
- **Symptom:** golden payloads differed on Windows: `—` → `â€"`.
- **Root cause:** ~54 text I/O sites without `encoding="utf-8"`; Windows default cp1252 decoded UTF-8 prompt/style files → every Windows distill sent corrupted prompt contracts to the LLM.
- **Fix:** explicit utf-8 at every text I/O site + `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` at CLI entry. Goldens now regenerate byte-identically on Windows.
- **Lesson:** an "environment-dependent test failure" can be a real product defect wearing a test costume. The 4 golden failures were the product corrupting its own LLM input.

### 9. Path separators leaked into artifacts
- **Symptom:** citations/`reconciliation.json`/snapshot maps contained `repo:src\scene.py` on Windows; `KeyError: 'src/main.py'` on lookups.
- **Fix:** `.as_posix()` at every artifact/citation WRITE boundary; OS-native paths only for filesystem access.
- **Lesson:** artifacts are a cross-machine interchange format — normalize at the boundary, not at the consumers.

### 10. Orchestrator's own script over-cut a file
- **Symptom:** trimming the legacy block from `dod_check.sh` also deleted two later legit sections.
- **Fix:** caught by reviewing the staged diff before commit; restored and re-cut surgically (start/end line match instead of cut-to-EOF).
- **Lesson:** the review-the-diff-before-commit rule applies to the orchestrator too, not just workers.

## Process

### 11. Ledger + honest gates kept everything recoverable
Every task: worker report → orchestrator re-verifies → diff review → commit with rationale. Plan checkboxes + completion note sealed at the end; deviations (baseline correction, sandbox protocol, deferred stage-wiring) recorded in the plan itself rather than papered over.
- **Lesson:** when the plan meets reality and loses, amend the plan visibly — the ledger is only useful if it's true.
