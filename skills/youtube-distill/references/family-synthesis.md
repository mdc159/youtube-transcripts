# Family Synthesis — multiple videos + local assets → per-topic docs

Load when the user asks to combine several videos (and optionally downloaded assets/notes) into one authoritative doc per topic family — e.g. three tutorials covering different workflows of the same toolchain.

## Principle

Each video is distilled **separately first**; synthesis happens over the per-video artifacts, never over raw transcripts merged prematurely. One video may span families, one family may span videos — the family boundary comes from the user's asset/topic structure, not from the video list.

## Workflow

1. **Extract all videos** (parallel background jobs are fine — see parent skill). Distill each with the style that fits (`auto` or explicit). Wait for all artifact sets to verify.
2. **Inventory local assets** the user pointed at (folders, JSONs, notes). Read them directly — asset bytes are evidence equal to video evidence. Extract dependency facts mechanically where possible (e.g. node types and model filenames from workflow JSONs) instead of trusting prose.
3. **Map evidence to families.** For each family gather: its videos (or segments), its assets, its notes. Overlaps (shared models, shared setup steps) belong in every family doc that needs them, plus a dedup note.
4. **Write one doc per family** at the user-specified location, each containing:
   - Node/pack/dependency manifest (exact names + versions where known)
   - Model manifest: file → exact destination path → source URL → gated? license notes
   - Workflow-specific settings and exact on-screen values
   - Known gotchas (version traps, naming traps, divisibility constraints, env vars)
   - Canonical sample inputs
   - Open questions the evidence did NOT resolve
   - Provenance: which video/artifact/asset each section came from (keep `seg#`/`t=`/`frame_` citations where they exist)
5. **Dedup pass across family docs**: shared models/steps listed identically in each doc (same name, same path, same source) — contradictions get flagged in BOTH docs, never silently resolved.
6. **Sweep the user's open questions** against transcripts + assets explicitly. Report per question: resolved-with-evidence / partially resolved / still open.
7. **Report** per-family doc paths, dedup notes, and the open-question ledger.

## Done when

- Every family has its doc at the agreed path.
- Every load-bearing claim traces to a video citation or a named asset file.
- The open-question ledger is explicit — nothing silently dropped.
