# Audit findings — 2026-05-07

First run of the `.audit/` three-way audit toolkit on this repo. Scope: `README.md`, `CLAUDE.md`, design spec, distill prompt contract (~950 lines, 198 verifiable claims). VPS arm disabled (this is a local CLI tool).

## Headline

| Total | MATCH | DRIFT | UNVERIFIABLE |
|---|---|---|---|
| 198 | 89 | 15 | 94 |

The raw count of "DRIFT" findings is misleading because the verifier produces several categories of false positive (see below). After triage, **1 real drift** was found and fixed; the remaining 14 are verifier limitations or stale references after a doc refresh.

## What was real

### 1. `vendor/claude-video/` → `vendor/claude_video/` in spec — FIXED

The design spec (`docs/superpowers/specs/...-design.md`) referenced the vendored toolkit at `vendor/claude-video/` (with hyphen) in 7 places, but the actual on-disk directory is `vendor/claude_video/` (with underscore — Python imports require it). The audit caught this on the first verify run. Fixed in the same commit chain as this report.

This is exactly the class of drift the audit was built to catch: a path that compiles cleanly in code but is described inconsistently in prose, where neither the test suite nor a casual review would ever flag it.

## False positives (verifier limitations)

These are flagged as DRIFT in the raw report but are not actual doc-vs-code mismatches. Catalogued so future audits can either suppress via `.audit_ignore.yaml` or motivate verifier fixes.

| Category | Examples | Why it's wrong |
|---|---|---|
| **Probe disabled misclassified as drift** | README L22, spec L44, L154 | Verification config has `allow_probes: false`. Behavioral claims that needed a probe to verify are returning "probe skipped: disabled" — that should classify as UNVERIFIABLE, not DRIFT. |
| **Placeholder literals** | README L10 (`Generated_Data/<title>/`), L100 (`frames/`) | The verifier interpreted angle-bracket placeholders and relative paths in docs as literal filesystem paths and looked for them under cwd. |
| **API-key-env-name confusion** | Spec L219 (gpt-4o uses `OPENAI_API_KEY`), L477, L478 | The verifier compared `api_key_env` *names* against the contents of env files. `OPENAI_API_KEY` is the *name* of an env var the profile reads at runtime, not a value that needs to be present in committed env files. |
| **Audit self-pollution** | Spec L71, contract L41 | The verifier searched the codebase for short strings (`extract -> distill`) and found matches inside its own `docs/audits/2026-05-07/claims.*.yaml` outputs. The verifier should exclude its own output directory from searches. |
| **Stale claim line numbers** | All 5 CLAUDE.md drifts on the second verify run | CLAUDE.md was refreshed *between* extract and the second verify. The claims still reference the old line numbers, so the doc resolver finds different content than what was extracted. Re-extract to re-audit. |
| **Multiple matches misclassified** | CLAUDE.md L13 (uv sync), L24 (download_transcript.py exists) | The verifier appears to flag claims as DRIFT when the search yields multiple matches, even when the underlying claim is true. |

## Doc-level outcomes

- **`README.md`**: 65 claims, 3 raw "drifts" — all verifier false positives. Doc is tightly aligned with code.
- **`CLAUDE.md`**: 23 claims extracted from the *legacy* CLAUDE.md. Most matched because `download_transcript.py` and `main.py` still exist for backward compat. The doc was structurally incomplete (missed everything from M4–M10), but the audit can't surface "missing content" — it only verifies extracted claims. CLAUDE.md was refreshed in this same commit chain to describe the full pipeline.
- **Design spec**: 84 claims, 7 raw "drifts" — 1 real (`vendor/claude-video` typo, fixed), 6 false positives.
- **Distill contract**: 26 claims, 1 raw "drift" — false positive (audit self-pollution on a `/tmp/` path).

## What this audit run is good at

Catching path/identifier drift between docs and code. The vendor-path typo would have stayed in the spec indefinitely without this kind of mechanical check.

## What this audit run is *not* good at (limitations)

- **Surfacing missing content**: a doc that describes 10 modules but the code has 20 isn't flagged. The audit can only verify what's explicitly claimed.
- **Behavioral claim verification with probes off**: requires `verification.allow_probes: true` and an environment where the probes can run safely.
- **Cross-file canonicalization**: when the same claim appears in multiple docs, the verifier doesn't reconcile them — it audits each file's claims independently.

## Recommended next steps

1. **Suppress recurring false positives**: add the categories above (probe-disabled, placeholder, env-name) to `.audit_ignore.yaml` so future runs are quieter.
2. **Re-extract for CLAUDE.md**: the file was rewritten; the next audit should re-extract its claims to get a clean line-number mapping.
3. **Verifier improvements** (toolkit work, separate repo at `.audit/`): exclude `docs/audits/` from code search; classify probe-skipped as UNVERIFIABLE not DRIFT; recognize angle-bracket placeholders.
4. **Schedule**: this was a one-shot pre-merge audit. Re-running on a cadence (e.g., per-release or quarterly) would surface drift introduced by new features.

## Reproducibility

```bash
# From repo root, with .audit/ toolkit present and OpenCode on PATH:
echo '{}' > .audit-local/vps-dump.full.json   # placeholder for --skip-vps run
ln -sf .audit audit                            # workaround for verify.py imports
uv run .audit/run.py --date 2026-05-07 --skip-vps --workflow three_way_audit
# (curate .audit-local/claims.draft.yaml → docs/audits/2026-05-07/claims.curated.yaml)
uv run .audit/run.py --date 2026-05-07 --skip-vps --skip-extract
```

Note: this run hit two toolkit bugs that required workarounds — concurrency=10 caused an OpenCode SQLite WAL contention that aborted the spec extract (re-ran sequentially), and `extract.py` reads the harness summary file instead of the output log when both exist (parsed the logs directly with `/tmp/parse_audit_logs.py`, not committed).
