# Three-way audit - 2026-05-07

- Total claims: 198
- Headline: 89 MATCH, 15 DRIFT, 94 UNVERIFIABLE

## Top drifts

- **CLAUDE.md:13** (DRIFT) — The dependency installation command is `uv sync`. → reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:1160:  claim_text: The dependency installation command is `uv sync`.
./docs/audits/2026-05-07/claims.curated.yaml:1161:  expected_value: uv sync
./docs/audits/2026-05-07/claims.curated.yaml:1931:  claim_text: The install command is uv sync.
./docs/audits/2026-05-07/claims.curated.yaml:1932:  expected_value: uv sync
./docs/audits/2026-05-07/claims.verified.yaml:1553:  claim_text: The dependency installation command is `uv sync`.
- **CLAUDE.md:16** (DRIFT) — The main transcript downloader is run with `uv run python download_transcript.py`. → reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:1173:  claim_text: The main transcript downloader is run with `uv run python download_transcript.py`.
./docs/audits/2026-05-07/claims.curated.yaml:1174:  expected_value: uv run python download_transcript.py
./docs/audits/2026-05-07/claims.verified.yaml:1585:  claim_text: The main transcript downloader is run with `uv run python download_transcript.py`.
./docs/audits/2026-05-07/claims.verified.yaml:1586:  expected_value: uv run python download_transcript.py
./docs/audits/2026-05-07/claims.verified.yaml:1595:    uv run python download_transcript.py
- **CLAUDE.md:19** (DRIFT) — The virtual environment can be activated with `source .venv/bin/activate`. → reconcile sources; vps says: ./docs/audits/2026-05-07/claims.verified.yaml:1615:  claim_text: The virtual environment can be activated with `source .venv/bin/activate`.
./docs/audits/2026-05-07/claims.verified.yaml:1616:  expected_value: source .venv/bin/activate
./docs/audits/2026-05-07/claims.verified.yaml:1625:    source .venv/bin/activate
./docs/audits/2026-05-07/claims.verified.yaml:1631:    The virtual environment can be activated with `source .venv/bin/activate`.
./docs/audits/2026-05-07/claims.verified.yaml:1634:    source .venv/bin/activate'
- **CLAUDE.md:24** (DRIFT) — The repository contains a script named `download_transcript.py`. → reconcile sources; vps says: path exists: download_transcript.py
- **CLAUDE.md:30** (DRIFT) — The repository contains `main.py`. → reconcile sources; vps says: path exists: main.py
- **README.md:10** (DRIFT) — Artifacts are stored under Generated_Data/<title>/. → reconcile sources; vps says: path missing: Generated_Data/<title>
- **README.md:22** (DRIFT) — Re-running extract.py skips work when outputs are still intact. → reconcile sources; vps says: probe skipped: disabled
- **README.md:100** (DRIFT) — Frame images are stored under a frames/ directory. → reconcile sources; vps says: path missing: frames
- **docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md:44** (DRIFT) — extract.py accepts --cookies-from-browser. → reconcile sources; vps says: probe skipped: disabled
- **docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md:71** (DRIFT) — run.py is a convenience command that runs extract then distill. → reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:273:  expected_value: extract -> distill
./docs/audits/2026-05-07/claims.verified.yaml:419:  expected_value: extract -> distill
./docs/audits/2026-05-07/claims.verified.yaml:429:    extract -> distill'
./docs/audits/2026-05-07/claims.verified.yaml:431:    extract -> distill'

## Drift by source

- docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md: 6 drift(s)
- CLAUDE.md: 5 drift(s)
- README.md: 3 drift(s)
- prompts/distill_contract_v1.md: 1 drift(s)

## Suggested fix list (grouped by file)

### CLAUDE.md
- L13: reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:1160:  claim_text: The dependency installation command is `uv sync`.
./docs/audits/2026-05-07/claims.curated.yaml:1161:  expected_value: uv sync
./docs/audits/2026-05-07/claims.curated.yaml:1931:  claim_text: The install command is uv sync.
./docs/audits/2026-05-07/claims.curated.yaml:1932:  expected_value: uv sync
./docs/audits/2026-05-07/claims.verified.yaml:1553:  claim_text: The dependency installation command is `uv sync`.
- L16: reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:1173:  claim_text: The main transcript downloader is run with `uv run python download_transcript.py`.
./docs/audits/2026-05-07/claims.curated.yaml:1174:  expected_value: uv run python download_transcript.py
./docs/audits/2026-05-07/claims.verified.yaml:1585:  claim_text: The main transcript downloader is run with `uv run python download_transcript.py`.
./docs/audits/2026-05-07/claims.verified.yaml:1586:  expected_value: uv run python download_transcript.py
./docs/audits/2026-05-07/claims.verified.yaml:1595:    uv run python download_transcript.py
- L19: reconcile sources; vps says: ./docs/audits/2026-05-07/claims.verified.yaml:1615:  claim_text: The virtual environment can be activated with `source .venv/bin/activate`.
./docs/audits/2026-05-07/claims.verified.yaml:1616:  expected_value: source .venv/bin/activate
./docs/audits/2026-05-07/claims.verified.yaml:1625:    source .venv/bin/activate
./docs/audits/2026-05-07/claims.verified.yaml:1631:    The virtual environment can be activated with `source .venv/bin/activate`.
./docs/audits/2026-05-07/claims.verified.yaml:1634:    source .venv/bin/activate'
- L24: reconcile sources; vps says: path exists: download_transcript.py
- L30: reconcile sources; vps says: path exists: main.py

### README.md
- L10: reconcile sources; vps says: path missing: Generated_Data/<title>
- L22: reconcile sources; vps says: probe skipped: disabled
- L100: reconcile sources; vps says: path missing: frames

### docs/superpowers/specs/2026-05-07-youtube-transcripts-claude-video-merge-design.md
- L44: reconcile sources; vps says: probe skipped: disabled
- L71: reconcile sources; vps says: ./docs/audits/2026-05-07/claims.curated.yaml:273:  expected_value: extract -> distill
./docs/audits/2026-05-07/claims.verified.yaml:419:  expected_value: extract -> distill
./docs/audits/2026-05-07/claims.verified.yaml:429:    extract -> distill'
./docs/audits/2026-05-07/claims.verified.yaml:431:    extract -> distill'
- L154: reconcile sources; vps says: probe skipped: disabled
- L219: reconcile sources; vps says: OPENAI_API_KEY not present in any env file
- L477: reconcile sources; vps says: OPENROUTER_API_KEY not present in any env file
- L478: reconcile sources; vps says: ['GROQ_API_KEY', 'OPENAI_API_KEY'] not present in any env file

### prompts/distill_contract_v1.md
- L41: reconcile sources; vps says: path missing: /tmp/opencode-task-extract-distill-contract-v1-md-4a18c2b1ec-summary.md

