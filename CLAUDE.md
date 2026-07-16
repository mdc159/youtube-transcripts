# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

A local CLI plus project skills that turn a YouTube URL or local video into citation-grounded, multimodal artifacts for agent workflows. Phase 1 (`yt-distill extract`) downloads the source, runs a 4-tier transcript chain, extracts and OCRs frames, classifies what's on screen, and writes an idempotent artifact tree. Phase 2 (`yt-distill distill`) reads those artifacts, optionally routes `auto` to the best style, builds an enriched + multimodal payload, calls a vision-capable LLM, and validates every citation in the result. `yt-distill run` chains both for one-shot use.

User-facing details live in `README.md`. Architectural rationale is in `docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md`.

## Entry points

| File | Purpose |
|---|---|
| `src/yt_distill/cli.py` | Single `yt-distill` console entry point; dispatches subcommands without changing their flags |
| `src/yt_distill/pipeline/extract.py` | Phase 1 orchestrator: source → transcript → frames → OCR → manifest |
| `src/yt_distill/stages/references.py` | Phase 1.5: harvest URLs (description/comments/transcript/OCR) → classify → snapshot repos pinned to SHA / fetch docs. Budgets: `--max-repo-mb`, `--max-fetches` |
| `src/yt_distill/pipeline/distill.py` | Phase 2 orchestrator: artifacts → enrich → frame select → reconcile (when repo snapshots exist) → LLM → markdown + JSON (+ `skills/<slug>/` bundle for `claude_skill`) |
| `src/yt_distill/pipeline/review.py` | Phase 3 quality gate: fresh-context reviewer sees only the bundle → gaps → targeted escalation → re-synthesis; cap `--max-iterations` (3) then ships `incomplete` |
| `src/yt_distill/stages/visual.py` | Phase 2.5 (standalone, not auto-wired): post-process distilled markdown to surface visual evidence — Tier 1 inline frame images / contact-sheet gallery / YouTube deep-links / verbatim code appendix (no LLM), Tier 2 Mermaid pipeline + reference tables + mindmap (one LLM call each). `enrich(out_dir, style_name=...)` is idempotent; `--no-llm` for Tier 1 only |
| `src/yt_distill/pipeline/run.py` | Convenience wrapper: `extract → distill` |
| `src/yt_distill/clean.py` | Storage management; dry-run by default |
| `src/yt_distill/core/models.py` | Profile resolution + `doctor` capability checks; also a CLI subcommand |
| `.archon/workflows/` | Archon workflow (`lesson-liberation.yaml`) wrapping extract → refs → distill → review |
| `.cursor/skills/` | Project-local agent skills for routing and output workflows |

## Library modules

| File | Purpose |
|---|---|
| `src/yt_distill/stages/registry.py` | Stage registration, dependencies, outputs, and cost-tier ordering |
| `src/yt_distill/core/manifest.py` | `artifact_manifest.json` read/write + per-file integrity tracking |
| `src/yt_distill/stages/transcript.py` | 4-tier chain: youtube-transcript-api → pytube → yt-dlp → whisper |
| `src/yt_distill/stages/frame_ocr.py` | RapidOCR wrapper, 5-class classifier (code / slide / ui / diagram / other), rapidfuzz dedup, `ocr.json` I/O |
| `src/yt_distill/stages/frame_select.py` | Style-aware perceptual-hash scene detection + anchored even-spacing + token-budget cap |
| `src/yt_distill/core/enrichment.py` | Splice frame OCR into transcript at frame timestamps |
| `src/yt_distill/core/payload.py` | Multimodal LLM payload builder (text + base64 images) |
| `src/yt_distill/core/citation.py` | Citation token regex (`seg#`, `frame_NNN_t-MM-SS`, `cluster_id=cN`, `t=MM:SS` incl. `H:MM:SS`/`MMM:SS`, `repo:path#Lx-Ly@SHA`) + extract + validate |
| `src/yt_distill/core/reconcile.py` | Cross-check transcript ↔ OCR code clusters ↔ pinned repo snapshots; conflicts flagged, never silently resolved; emits `reconciliation.json` + payload evidence block |
| `src/yt_distill/output/skill_bundle.py` | `claude_skill` bundle writer: `skills/<slug>/{SKILL.md, assets/, reference/, provenance.json}` |
| `src/yt_distill/output/render.py` | `distill_result.json` → Obsidian-ready markdown with frontmatter |
| `src/yt_distill/core/video_profile.py` | Lightweight transcript/OCR signal router for `auto` style selection |
| `src/yt_distill/core/env_bootstrap.py` | Per-entry-point bootstrap: repo-root `.env` loading + DNS fallback arming |
| `src/yt_distill/core/dns_fallback.py` | DoH fallback resolver (Cloudflare → Google) for networks that hijack/filter port-53 DNS |

## Config & contracts

- `models.yaml` — model profiles. Default `gemini-3.5-flash` (OpenRouter `google/gemini-3.5-flash`; `gemini-3.5-flash-high` pins reasoning_effort=high for review-loop escalation). Adding a new profile is one YAML entry, zero code changes.
- `prompts/distill_contract_v1.md` — the citation contract sent to every LLM call. Every technical claim in output must cite at least one of: transcript segment, frame, cluster, or timestamp range. `prompts/distill_contract_v2.md` adds `repo:path#Lx-Ly@SHA` citations + evidence-authority/conflict rules; `src/yt_distill/pipeline/distill.py` selects v2 automatically when reference following has pinned repo snapshots (`prompt_contract_version` in `distill_result.json` records which ran).
- `styles/<name>.md` — user-editable style overlays. Available: `coding_agent`, `knowledge_base`, `diy_project`, `human_tutorial`, `claude_skill`. `human_tutorial` (human-reader tone) and `claude_skill` (self-sufficient agent skill bundle) are explicit-only — `auto` never routes to them.
- `.cursor/skills/video-distill-router` — meta skill for choosing between video workflows.
- `.cursor/skills/youtube-coding-agent`, `.cursor/skills/youtube-diy-project`, `.cursor/skills/youtube-knowledge-base`, `.cursor/skills/youtube-human-tutorial`, `.cursor/skills/youtube-claude-skill` — output workflow skills that mirror the style overlays. Keep skills and `styles/` in sync when editing either.

## Vendored

`vendor/claude_video/` — frozen at upstream commit `755c157`. Frame extraction (`frames.py`) and Whisper helpers (`whisper.py`) are called from `src/yt_distill/pipeline/extract.py` and `src/yt_distill/stages/transcript.py`. Note the underscore directory name; Python imports require it. Upstream pin and any local modifications are documented in `vendor/claude_video/UPSTREAM.md`.

## Commands

```bash
uv sync                                                   # install deps (uses uv; Python 3.11–3.12)
uv run pytest                                             # unit + fast integration
uv run pytest -m integration                              # only the slow ones (real ffmpeg, real OCR)
bash scripts/dod_check.sh                                 # full end-to-end gate (spec §9)

uv run yt-distill run "<url-or-path>" <style>                  # one-shot extract + distill
uv run yt-distill extract "<url-or-path>"                      # phase 1 only
uv run yt-distill refs <title-dir>                             # phase 1.5: links → repo snapshots @SHA / docs
uv run yt-distill distill <title-dir> <style> --model X        # phase 2; --dry-run-payload to skip LLM call
uv run yt-distill distill <title-dir> claude_skill             # phase 2 + reconciliation + skills/<slug>/ bundle
uv run yt-distill review <title-dir>                           # phase 3: downstream-hat review loop
uv run yt-distill distill <title-dir> auto --dry-run-payload   # route to a style without a live LLM call
uv run yt-distill doctor --profile <name>                      # validate a model profile
uv run yt-distill clean --delete-video --older-than 30d --apply   # disk cleanup
```

## Output

Artifacts live under `Generated_Data/<title>/`. Frame paths in `ocr.json` are relative to that dir (cross-machine portable). The final markdown has Obsidian-style YAML frontmatter with citation counts, quality grades, model profile, and prompt-contract version.

## Conventions worth knowing

- Idempotency: re-running `yt-distill extract` skips work whose outputs are still intact (uses manifest file-integrity hashes). `--force` bypasses; `--force-ocr` re-runs only OCR.
- Routing: passing `auto` to `yt-distill distill` or `yt-distill run` uses `yt_distill/core/video_profile.py` to score coding, DIY, and knowledge-base signals from transcript text plus OCR/frame classes. Explicit styles always win.
- Visual evidence: frame selection is style-aware. Coding can include code frames when image context matters; DIY prioritizes slide/UI/diagram step evidence; knowledge-base keeps the previous non-code slide/diagram bias.
- Transcript chain: `--cookies-from-browser` is threaded into every `yt-dlp` call (probe in `yt_distill/pipeline/extract.py:_probe_source`, captions in `yt_distill/stages/transcript.py:_fetch_via_ytdlp`, download in `yt_distill/pipeline/extract.py:_download_video`). On WSL prefer `chrome`/`edge` — Windows-side Firefox profiles aren't reachable. When tiers 1-3 fail and `GROQ_API_KEY` / `OPENAI_API_KEY` is set, `_do_transcript` reuses the cached video, extracts audio via the vendored `extract_audio` helper, and falls back to Whisper. Tier 1 (`youtube-transcript-api`) requires a real video ID; `yt_distill.stages.transcript._extract_video_id` parses it from any YouTube URL form.
- Citations: `seg#NNN` (transcript), `frame_NNN_t-MM-SS` (specific frame), `cluster_id=cN` (deduped code-frame cluster), `t=MM:SS` or `t=MM:SS–MM:SS` (timestamp). Unresolved citations make `yt-distill distill` exit non-zero with a banner in the markdown.
- Errors are `RuntimeError`, not `SystemExit`, in helpers — catchable from Python callers.
- No VPS / deployment. This is a local CLI tool.

## Three-way audit

`.audit/` is a vendored documentation-vs-code drift detector. Configuration at `.audit.config.yaml`; results land in `docs/audits/YYYY-MM-DD/`. Run with `uv run .audit/run.py --skip-vps --workflow three_way_audit` (this repo has no VPS arm).
