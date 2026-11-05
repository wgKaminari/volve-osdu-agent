# CLAUDE.md - volve-osdu-agent

## What this project is

An AI agent that converts raw files from Equinor's open Volve dataset (well logs, well paths, petrophysical report PDFs) into OSDU records (Well, Wellbore, WellLog, WellboreTrajectory, WellboreMarkerSet) packaged as an OSDU ingestion manifest. Every output value carries provenance, every record is validated, uncertain or conflicting values are routed to human review, and the whole pipeline is measured against independent ground truth.

Owner: Vyacheslav Snoz (GitHub: wgKaminari). Personal portfolio project, public on GitHub.
Private notes (if present) live in docs/private/, which is gitignored and must never be committed.

Before any task, read `docs/PROJECT_GUIDE.md`. It is the source of truth for scope, data, architecture, evaluation and milestones. If this file and the guide disagree, the guide wins.

## How we work

- Work one milestone at a time (guide, section 9). At the end of each milestone: run tests, summarize what was built, list open questions, then stop and wait for review.
- Prefer small, reviewable commits with clear messages.
- Ask the owner before: adding a heavy dependency, changing metric definitions, editing gold labels, changing scope, or publishing anything.
- When unsure about an OSDU field, a reference value or a domain term, say so and propose an option. Don't guess silently.

## Core design principles (non-negotiable)

- **LLM proposes, code computes, validators judge.** The LLM chooses mappings, resolves names and extracts facts from prose. Numeric values are read by deterministic code from the source (LAS/DLIS/well path), never typed by the LLM.
- **Provenance for every value.** Each populated field records source_file, locator (LAS mnemonic, row, PDF page + quote) and method (parsed | llm_extracted | derived).
- **Grounding check for LLM extractions.** An llm_extracted value must come with a verbatim quote; code checks the quote exists in the source text and the value appears in the quote. If the check fails, the value is dropped and flagged.
- **Abstain instead of guessing.** If a value is not in the inputs, leave it null and record why.
- **No ground-truth leakage.** The agent never reads `data/gold/` or the NPD/well-picks files during a run. Only `src/volve_osdu/eval/` may read gold.
- **Human review is a feature.** Conflicts between sources (e.g. the 15/9-F-12 GR log going to 4186.7 m MD while the actual well path ends at 3520 m) become review flags with both values and their sources.

## Hard rules

- Never fabricate data, results, metrics or citations. If a run fails, report the failure.
- Gold labels created or drafted with AI help must be marked `reviewed: false` until the owner reviews them. Never report metrics on unreviewed gold without saying so.
- Never commit raw data (`data/raw/`), `.env`, API keys or LLM cache contents.
- Never use employer code, data, accounts or API keys.
- Cache every LLM call on disk (key = hash of model + prompt + params) so evals are reproducible and stay inside free-tier limits.
- Pin dependency versions and data sources (commit hashes are in the guide).

## Stack

- Python 3.12, uv for env and deps, ruff (lint + format), pytest, type hints everywhere.
- langgraph (agent), OpenAI-compatible client via env vars (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`); default provider GitHub Models free tier.
- osdu-python-models (Equinor, Pydantic v2 OSDU models) + jsonschema (pinned OSDU schemas).
- lasio (LAS), dlisio (DLIS, Equinor), pdfplumber (PDF text), pandas, pydantic-settings.

## Commands

```bash
uv sync                                   # install
bash scripts/download_data.sh             # fetch pinned data + schemas into data/raw
uv run python scripts/build_gold.py       # build held-out ground truth into data/gold
uv run pytest -q                          # tests
uv run ruff check . && uv run ruff format .
uv run volve-osdu run --wellbore "15/9-F-12"      # one wellbore -> outputs/<run_id>/
uv run volve-osdu eval --systems rules,llm_only,agent   # full evaluation -> docs/results.md
```

(Implement these commands as the milestones progress; keep this list accurate.)

## Layout

```
src/volve_osdu/ingest/     file inventory + LAS/DLIS/well path/PDF readers (deterministic)
src/volve_osdu/osdu/       id builders, record builders, manifest, reference-value lookup
src/volve_osdu/validate/   jsonschema, Pydantic, business rules, provenance + grounding checks
src/volve_osdu/agent/      LangGraph graph, tools, prompts/, llm client, cache
src/volve_osdu/eval/       gold loading, metrics, bootstrap CIs, baselines, report
scripts/                   data download, gold build
configs/                   wells.yaml (wellbores + bundles), settings.yaml
tests/                     unit tests per reader/validator + one end-to-end test
outputs/                   run outputs (gitignored)
docs/                      PROJECT_GUIDE.md, architecture.md, results.md
```

## Code style

- Small pure functions; readers return typed dataclasses/Pydantic models, not raw dicts.
- Every reader and validator has unit tests with a tiny fixture file.
- Log with `logging`, not `print`. No silent `except`.
- Prompts live in `src/volve_osdu/agent/prompts/*.md`, versioned, with the expected JSON schema.
