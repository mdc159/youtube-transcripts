# youtube-transcripts — Architecture Map (reference for the delta build)

Captured from a full read of the codebase. Absolute-relative to repo root.
This is reference material for the Lesson Liberation delta build (see PLAN.md).

> `main.py` is a stub — ignore it. Four real entry points: `run.py`,
> `extract.py`, `distill.py`, `models.py` (+ `clean.py`, `enrich.py`,
> legacy `download_transcript.py`).

## Pipeline
`extract.py` (Phase 1: source → transcript → frames → OCR → manifest, idempotent)
→ `distill.py` (Phase 2: artifacts → enrich → frame-select → LLM → markdown+JSON).
`run.py` chains them in-process (imports both, calls their `main()`), handing off
the title by picking the most-recently-modified `Generated_Data/` subdir.

## On-disk layout — `Generated_Data/<title>/`
```
artifact_manifest.json    extract_meta.json
<title>_formatted_transcript.txt   (start_seconds|text per line)
<title>_clean_text.txt             (space-joined, no timestamps)
<title>_enriched_transcript.md
ocr.json   selected_frames.json   payload.json (only --dry-run-payload)
frames/frame_NNN_t-MM-SS.jpg
<title>_<style>.md   <title>_<style>.distill_result.json
```
Frame paths in `ocr.json` are relative to `out_dir` (portable).

## Manifest (`manifest.py`)
`artifact_manifest.json`. `derive_source_id`: YouTube→`yt:<id>`, local→
`local:<sha1[:12]>`, web→`web:<sha1[:12]>` (+`#start-end` for clips). Idempotency
via per-file sha256 / dir frame_count (`file_intact`). `record_file` only accepts
`section=="extract"` today. **Key finding: `distill.py` never calls
`add_distill_run()`/`save()` — `distill_runs` stays `[]` on disk. The review loop
must add those calls (and the missing `save()`).**

## Style router (`video_profile.py`)
`auto` scores coding/diy/knowledge from transcript+OCR signals. `human_tutorial`
is deliberately NOT in `STYLES` (explicit-only). A style is just a file
`styles/<name>.md` (H1 + `## Output Format` numbered `### N. Section` + `## Rules`);
sections are authoritative per contract rule 3. No registry/enum. Unknown explicit
style fails at `distill.py:90-93`. Single-file output is hard-coded at
`distill.py:247-249` — a bundle style needs a new render branch.

## distill_result.json
Built at `distill.py:212-236` (no golden fixture — the dict literal is the schema
source of truth). Markdown path → `{"summary": <raw markdown>}`; legacy JSON path
adds `key_points/steps/code_blocks/tools_mentioned/visual_evidence_used/
open_questions`. Always carries `schema_version, source_id, title, model_profile,
prompt_contract_version, quality{}, warnings[], token_usage{}, citations{}`.

## Citation contract (two places)
- `citation.py` — machine validator. Regexes: `seg#(\d+)`,
  `frame_\d{3}_t-\d{2}-\d{2}`, short `frame_(\d{3})`, `cluster_id=([\w]+)`,
  `t=\d{2}:\d{2}(?:[–-]\d{2}:\d{2})?`. `ResolutionContext(segment_ids, frame_ids,
  cluster_ids)`. Timestamps always resolvable. Unresolved → `distill.py` exits 1 +
  banner.
- `prompts/distill_contract_v1.md` — NL rules sent as system prompt. Rule 1
  mandates a citation on every technical claim (overrides style). `prompt_contract
  _version` field exists for versioning (bump to v2 for the repo-citation addition).

## Models (`models.yaml` / `models.py`)
`default: gemini-3-flash`. Profiles carry `base_url, model, vision, reasoning,
api_key_env, max_images, max_image_bytes`. **All LLM calls use the OpenAI SDK
pointed at OpenRouter** — no `anthropic` package. Call sites: `distill.py:188-192`,
`models.py` doctor probes, `enrich.py:304-317`. `resolve()` precedence:
`--model > $DISTILL_MODEL > yaml default`. New model = one YAML entry, zero code.
Adding native Anthropic = new provider path OR keep OpenRouter-proxied
`anthropic/*` models. No per-phase model map exists yet.

## Frames/OCR (`frame_ocr.py`, `frame_select.py`)
5-class classifier (code/slide_text/ui/diagram/other). `dedup_code_frames`
(rapidfuzz token_set_ratio ≥0.85) assigns `cluster_id` to CODE frames.
`ocr.json`: `{video{title,duration_seconds}, frames[{path,timestamp_seconds,
ocr_text,ocr_confidence,frame_class,class_confidence,cluster_id,ocr_error}]}`.
Frame selection is style-aware (`coding_agent` includes CODE; others exclude).
**Targeted timestamp grabs are NOT first-class** — only `--start/--end` clip. The
extraction primitive is vendored `cv_frames.extract(video,out_dir,fps,resolution,
max_frames,start_seconds,end_seconds)`; a per-timestamp `ffmpeg -ss` mode must be
added for the review loop's targeted grabs.

## Conventions
Python 3.11–3.12, `uv` (`pyproject.toml` deps + committed `uv.lock`). Flat
top-level modules imported by bare name; `from __future__ import annotations`.
Logging = `print("[phase] ...")`, errors to stderr. Helpers raise `RuntimeError`
not `SystemExit`. JSON artifacts `indent=2` (manifest/ocr/selected/meta also
`sort_keys=True`). Golden tests monkeypatch `distill.doctor`, run
`--dry-run-payload`, structurally compare payloads. `scripts/dod_check.sh` greps
for `TODO`/`XXX` → none allowed in shipped source. Vendored `claude_video/` frozen
at `755c157`. Keep `styles/<name>.md` and `.cursor/skills/youtube-<name>/SKILL.md`
in sync.

## Extension points (the 5 deltas)
- **(a) Reference Follower** — new `reference_follower.py`, run inside `extract.py`
  after transcript+frames. `yt-dlp --dump-json` already yields `description`;
  capture it. URL regex near `video_profile._COMMAND_OR_PATH_RE`. Clone/pin via
  subprocess (mirror `extract._download_video`). Persist `references.json` +
  `refs/<slug>@<sha>/` snapshots; extend `manifest.record_file` allowed sections;
  add idempotency gate like `_do_frames`; teach `clean.py`.
- **(b) Reconciliation** — new stage/module invoked in `distill.py` after payload
  build. Add `repo:path#L10-L40@SHA` to `citation.py` (regex + `kind=="repo"` +
  `ResolutionContext.repo_refs`) and to the contract (bump to v2 /
  `prompt_contract_version:2`). Conflicts → `warnings[]`.
- **(c) claude_skill style** — `styles/claude_skill.md` (explicit-only). Bundle
  emission = new render branch at `distill.py:247-249` →
  `skills/<slug>/{SKILL.md,assets/,reference/,provenance.json}`. Mirror
  `.cursor/skills/youtube-claude-skill/SKILL.md`.
- **(d) diy_project extension** — markdown edit to `styles/diy_project.md`
  `## Output Format` (add theory_of_operation; canonicalize BOM/tools/cautions).
  Mirror the Cursor skill.
- **(e) Downstream-Hat Review Loop** — new `review_loop.py` invoked in `distill.py`
  after first synthesis; fresh LLM client per iteration; cap 3; persist iterations
  via `manifest.add_distill_run()` (+ add the missing `save()`). Targeted
  escalation needs the per-timestamp frame-grab mode (see Frames). Guard behind a
  `--review` flag threaded through `run.py`.
None of the five require touching vendored `claude_video`.
