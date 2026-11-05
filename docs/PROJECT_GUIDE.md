# volve-osdu-agent - Project Guide

Owner: Vyacheslav Snoz · Written 2026-11-05 · Target: v0.1.0 public on GitHub by 2026-11-13

This guide is the source of truth for the project. `CLAUDE.md` holds the working rules for Claude Code; this file holds the what and why.

## 0. The project in plain words

Oil companies hold decades of well data in old file formats, scattered reports and spreadsheets. They are moving it into OSDU, a standard data platform for the energy industry. Today that migration is largely manual: people read files and reports and map every value into the right OSDU field. It is slow, expensive and error-prone.

This project builds an AI agent that does that mapping for Equinor's own open Volve data:

- It takes the raw files for one wellbore (well log files, well path, petrophysical report PDF).
- It works out what each file is, which wellbore it belongs to and which OSDU records it needs.
- It maps every value into OSDU format, reading numbers with code and using the LLM only for judgement (names, curve types, units, facts written in report prose).
- It checks its own output: schema validation, business rules, provenance and grounding. Anything uncertain or contradictory goes to a human review list.
- It outputs a ready-to-ingest OSDU manifest plus a review report.

Then we measure it: field accuracy against independent ground truth (Norwegian Offshore Directorate data and Equinor's own formation picks), compared with a rules-only baseline and an LLM-only baseline.

Headline we are aiming for (fill in real numbers only after the eval runs):

> "An AI agent that converts Equinor's open Volve data into OSDU records: X% field accuracy against official ground truth, Y% of LLM-extracted facts grounded in a verbatim source quote, 100% of records passing validation, and every conflict routed to human review."

## 1. Why this project

| Capability | Where this project shows it |
|---|---|
| Design, develop and test agentic AI solutions | LangGraph agent with tools, a validation loop and human review |
| Prompting strategies, retrieval systems, evaluation approaches | Versioned prompts, reference-value lookup, full eval harness with baselines and CIs |
| LLMs and multimodal AI | Structured extraction from report PDFs plus structured files |
| Production deployment, measure performance and quality | Provenance, deterministic validators, caching, cost/latency metrics, reproducible runs |
| Enterprise knowledge, data and business processes | OSDU ingestion is a real business process at Equinor |
| Agent frameworks (LangGraph / MAF) | LangGraph core; MAF port optional (section 9, stretch) |
| Responsible AI | Abstention, grounding checks, human-in-the-loop, limitations section |

Industry relevance: Equinor actively maintains OSDU tooling on GitHub, including equinor/osdu-python-models (the Pydantic models this project uses) and equinor/osdu-mcp-poc. Both are by Steinar Hjellvik. Volve is Equinor's flagship open dataset. No public project found (2026-11-05) combines Volve and OSDU; existing Volve AI projects are chatbots over reports.

Closest existing work: github.com/mehmetkadriumay/agentic-osdu-data-preparation (generic agentic OSDU data-prep tooling with MCP and a review UI, Sept 2026). Read it for ideas only; don't copy code. Our differentiators: (1) Equinor's own Volve data end to end, (2) accuracy measured against independent ground truth (NPD + Equinor well picks) with baselines and CIs, (3) grounding checks on facts extracted from report prose.

## 2. Background

### 2.1 Volve

Oil field in the Norwegian North Sea, operated by Equinor (then Statoil), produced 2008-2016. In 2018 Equinor released about 40,000 files: logs, reports, well paths, production, seismic, reservoir models. Wellbores are named like 15/9-F-12, where 15/9 is the block and F the platform. A suffix like A, B or T2 marks a sidetrack drilled from a parent wellbore.

### 2.2 OSDU

Open Subsurface Data Universe, an industry standard (The Open Group OSDU Forum). Data is stored as JSON records, each with a kind (type + version), acl, legal and a data block. Main groups used here:

- master-data: Well, Wellbore (the physical things)
- work-product-component (WPC): WellLog, WellboreTrajectory, WellboreMarkerSet (data about the things)
- dataset: File.Generic (the bulk file, e.g. curve values as Parquet)
- reference-data: controlled vocabularies (units, curve types, measurement types)

Records go in through a Manifest (`osdu:wks:Manifest:1.0.0`) that bundles MasterData, WorkProduct/WorkProductComponents and Datasets.

### 2.3 Input file types

- LAS (text): header (well name, coordinates, elevation, depth range, null value) plus a curve table. Read with lasio.
- DLIS (binary): richer log format. Read with dlisio (Equinor's library).
- Well path / deviation survey (text table): MD, inclination, azimuth, TVD, X/Y.
- Petrophysical report (PDF): prose and tables with TD, kick-off point, formation tops, fluid content and data-quality remarks.

A glossary is in section 14.

## 3. Goal, scope and success criteria

### 3.1 In scope (MVP)

- 13 LAS wellbores (list in 4.3) end to end: Well, Wellbore, WellLog, WellboreTrajectory (where a well path exists), Manifest.
- Header facts from LAS + PDF: canonical name, parent well, sidetrack parent, KB elevation, total depth (MD), kick-off point, surface lat/lon, field, operator.
- Curve mapping: mnemonic + unit + description -> OSDU LogCurveTypeID + UnitOfMeasure IDs.
- Validation, provenance, grounding checks, review flags.
- Evaluation against gold with 3 systems (rules-only, LLM-only, agent) and bootstrap CIs.

### 3.2 Stretch (only after MVP is green)

- DLIS wellbores (10 more) via dlisio.
- WellboreMarkerSet from PDF prose and tables, evaluated against Equinor well picks.
- Stress test: perturbed inputs (renamed files, ft instead of m, missing header lines).
- Small viewer (static HTML report or Streamlit) for one wellbore: inputs, records, flags.
- Port the agent graph to Microsoft Agent Framework (MAF) and compare.

### 3.3 Non-goals

- No real OSDU instance or ingestion API calls. Output is files only.
- No petrophysical interpretation (we don't compute porosity, we map existing data).
- No fine-tuning.

### 3.4 Success criteria

- `volve-osdu run` works for every MVP wellbore and writes manifest, provenance and review files.
- 100% of emitted records pass validation (or the run lists exactly why not).
- Eval report with per-field accuracy, CIs and baseline comparison, reproducible from cache.
- README a newcomer understands in 2 minutes, with an honest limitations section.

## 4. Data

### 4.1 Sources (pinned)

| Source | What | Pin | Licence |
|---|---|---|---|
| github.com/andymcdgeo/spwla_volve | Per-wellbore folders: LAS/DLIS logs, petrophysical report PDFs, Well_picks_Volve_v1.dat (formation tops), VOLVE_INVENTORY.xlsx | commit c293edf37c1b567b8dc9c81ea88f2cf288eab423 | Extracted from Volve -> Equinor Open Data Licence |
| github.com/awgeo/Volve_field_data | input_data/wellpaths/*_ACTUAL (well paths), input_data/wellheaders/NPD_wellbore_* (NPD headers), input_data/lithostrat/* (NPD formation tops, exploration wells), checkshots, LAS | commit 7cdecf1f1d24811d21bb2e2f379ff048404f4ce7 | Volve -> Equinor Open Data Licence; NPD data -> Norwegian open government licence (NLOD), confirm on factpages.sodir.no |
| github.com/equinor/osdu-python-models | Pydantic models + pinned schemas schemas/M27.1/ (data-definitions v0.30.1) | PyPI osdu-python-models==0.8.1 | Apache-2.0 |
| github.com/equinor/osdu-mcp-poc | schemas/manifest/Manifest.1.0.0.json and other schemas (DD v0.29.1) | latest main at download time; record hash | Apache-2.0 |
| OSDU data-definitions (community.opengroup.org) | Reference values (UnitOfMeasure, LogCurveType, VerticalMeasurementType, etc.) | tag v0.30.1 to match M27.1 | Apache-2.0 |

Volve licence essentials: credit "Equinor and the Volve licence partners", link the licence terms, don't sell the data, don't present it in a misleading way. Put an attribution section in the README. Don't commit raw data. `scripts/download_data.sh` clones the pinned commits into `data/raw/`. Small derived files (gold CSVs, curve-label CSV) may be committed with attribution.

Claude Code: locate the reference-value files inside data-definitions v0.30.1 yourself (they're published as reference-data manifests). Record the exact paths in `scripts/download_data.sh`.

### 4.2 Facts verified on 2026-11-05

- The LAS header for 15/9-F-12 (WLC_PETRO_COMPUTED_OUTPUT_1) has STRT 3102.102 m, STOP 3505.8096 m, STEP 0.1524 m, NULL -999.25, COMP STATOILHYDRO, LAT 58.441713, LON 1.887480, ELEV 54.9 m KB, and curves BVW, KLOGH, PHIF, SW, VSH.
- **Real in-input conflict (demo case):** 15/9-F-12 WLC_PETRO_COMPUTED_INPUT_1.LAS has GR data down to 4186.7 m MD (4,375 non-null rows below 3520 m), but the actual well path F-12_ACTUAL ends at 3520.00 m MD. A log deeper than the hole's final survey station should never be ingested silently. The agent must raise a warn flag with both sources.
- **Source vs gold disagreement:** both F-12 LAS files say KB elevation 54.9 m, while the NPD header (gold) says KBE 54.0 and TD 3520.0 m. The agent can't see NPD, so this is not a review flag. It shows that gold can use a different datum. Mark such gold rows disputed, report them separately, and never "fix" gold to match the agent.
- PDF text richness varies: the F-1 report is text-rich, but the F-12 report gives only ~3.9 KB of text (mostly figures and tables as images). Page images + a vision model is a stretch option; log which PDFs are image-heavy.
- The F-1 report PDF (15_9-F-1/PETROPHYSICAL_REPORT_1.PDF, which also covers F-1 A and F-1 B) states "TD of 15/9-F-1 was 3632 m MD RKB" (NPD: 3632.0), and for F-1 A "KOP @ 2620 m MD RKB" and "TD @ 3682 m MD RKB" (NPD: 2620.0 and 3682.0). So PDF prose is a real, checkable source.
- But for F-1 B the report says "KOP @ 2617 m MD RKB" while NPD says 2604.0: a 13 m report-vs-gold disagreement. The agent should extract 2617 (that's what the input says). Score it against gold as disputed and discuss it in the results.
- Well_picks_Volve_v1.dat has 557 lines (picks + per-well headers) with MD/TVD/TVDSS per surface, e.g. about 58 pick lines for the F-1 family and 64 for the F-15 family. The parser must handle the fixed-width layout, sidetrack names with spaces (NO 15/9-F-1 A) and Qlf codes (ER/FP/FO/NL/NR).
- NPD formation tops in awgeo lithostrat/ cover exploration wells (15/9-19 A/B/SR...), not the F wells. For F wells use Well_picks.

### 4.3 Wellbore bundles (from spwla_volve folders)

LAS = number of LAS files, DLIS = number of DLIS files, PDF = has petrophysical report.

| Folder | Canonical name | LAS | DLIS | PDF | Phase |
|---|---|---|---|---|---|
| 15_9-19A | 15/9-19 A | 2 | 0 | no | MVP |
| 15_9-19BT2 | 15/9-19 BT2 | 2 | 0 | no | MVP |
| 15_9-19SR | 15/9-19 SR | 3 | 0 | no | MVP |
| 15_9-F-1 | 15/9-F-1 | 2 | 0 | yes | MVP |
| 15_9-F-1A | 15/9-F-1 A | 2 | 0 | yes | MVP |
| 15_9-F-1B | 15/9-F-1 B | 2 | 0 | yes | MVP |
| 15_9-F1C | 15/9-F-1 C | 2 | 0 | yes | MVP |
| 15_9-F-11 | 15/9-F-11 | 1 | 1 | yes | MVP |
| 15_9-F11A | 15/9-F-11 A | 2 | 1 | yes | MVP |
| 15_9-F11B | 15/9-F-11 B | 2 | 1 | yes | MVP |
| 15_9-F11 T2 | 15/9-F-11 T2 | 2 | 1 | yes | MVP |
| 15_9-F12 | 15/9-F-12 | 2 | 0 | yes | MVP |
| 15_9-F15D | 15/9-F-15 D | 2 | 1 | yes | MVP |
| 15_9-F-4, F-5, F-10, F14, F15, F15A, F15B, F15C | ... | 0 | 2-3 | yes | Stretch (DLIS) |
| 15_9-F-9, F-9A | ... | 0 | 1 | no | Stretch |
| 15_9-F-7 | 15/9-F-7 | 0 | 0 | no | Skip (LAS exists in awgeo) |

Notes:

- Folder names are deliberately inconsistent (15_9-F11 T2, 15_9-F1C). Name resolution is a real task for the agent. Note that "F-11 T2" is marked "NOT ON NPD" in the awgeo well-path folder.
- Well paths exist in awgeo for most F wellbores (F-12_ACTUAL, F-1 A_ACTUAL, ...). Some files are plans or prototypes (F-10 A rev#6 PROTOTYPE, F-9A ... PLAN). The agent must not treat a plan as the actual trajectory: exclude it and flag it.
- Exploration wells (15/9-19 *) have headers in NPD_wellbore_exploration_all_AW EDIT_FINAL.xls. Verify that.

### 4.4 Ground truth (held out, evaluation only)

| Gold file (build with scripts/build_gold.py) | From | Used to score |
|---|---|---|
| data/gold/wellbore_headers.csv | NPD development + exploration headers (awgeo) | name, parent, KB elevation, TD MD, KOP, lat/lon, field, operator |
| data/gold/markers.csv | Well_picks_Volve_v1.dat (+ NPD lithostrat for 15/9-19 *) | marker name + MD (stretch) |
| data/gold/curve_labels.csv | Hand-labelled: mnemonic, LAS unit -> OSDU UoM ID + LogCurveType ID | curve mapping accuracy |
| data/gold/conflicts.csv | Hand-listed known conflicts (e.g. F-12 KB) + injected ones | review-flag precision/recall |

Rules:

- The agent and baselines never read NPD headers, Well_picks or data/gold/.
- curve_labels.csv: Claude Code may draft it, but each row needs `reviewed: true` by the owner before it counts. Report the share of reviewed labels in the results.
- Some NPD fields can't be recovered from the inputs (e.g. spud date if no source mentions it). build_gold.py marks each gold field as `recoverable: true/false` after a source search. The correct output for a non-recoverable field is null. Score that as correct abstention.

## 5. OSDU target

### 5.1 Kinds and Python models (osdu-python-models 0.8.1)

| Record | kind | Python model |
|---|---|---|
| Well | osdu:wks:master-data--Well:1.5.0 | osdu_models.masterdata.well.v1_5_0.Data |
| Wellbore | osdu:wks:master-data--Wellbore:1.5.1 | osdu_models.masterdata.wellbore.v1_5_1.Data |
| WellLog | osdu:wks:work-product-component--WellLog:1.5.0 | osdu_models.workproductcomponent.well_log.v1_5_0.Data (+ Curve) |
| WellboreTrajectory | osdu:wks:work-product-component--WellboreTrajectory:1.4.0 | osdu_models.workproductcomponent.wellbore_trajectory.v1_4_0.Data |
| WellboreMarkerSet | osdu:wks:work-product-component--WellboreMarkerSet:1.5.1 | osdu_models.workproductcomponent.wellbore_marker_set.v1_5_1.Data |
| Manifest | osdu:wks:Manifest:1.0.0 | jsonschema from osdu-mcp-poc schemas/manifest/ |

Key facts:

- Only kind, acl and legal are required at record level. Almost all data fields are optional, so schema-valid is a low bar. Our real quality signal is field accuracy plus business rules.
- WellboreTrajectory requires WellboreID, TopDepthMeasuredDepth, BaseDepthMeasuredDepth and VerticalMeasurement.
- osdu-python-models types the data block only, strips string format, and uses extra='allow'. So validate with both Pydantic (types) and jsonschema against the pinned schema (patterns, enums, $refs), plus our own rules.
- Bulk values (curve samples, trajectory stations) don't go in the WPC record. Write them as Parquet next to the manifest, and reference them via a dataset--File.Generic record.

### 5.2 Field mapping, starting point (confirm each against the schema)

| Fact | OSDU target | Source | Method |
|---|---|---|---|
| Wellbore name | Wellbore FacilityName; NameAliases for 15_9-F-12, NO 15/9-F-12 | LAS WELL/UWI, folder, PDF title | LLM resolves, code normalizes |
| Parent well | Wellbore WellID -> Well record (15/9-F-12 -> well 15/9-F-12; sidetracks share the parent's well) | name rules + LLM | derived |
| Sidetrack parent | Wellbore KickOffWellbore | PDF ("side-tracked from F-1") | llm_extracted |
| KB / RKB elevation | VerticalMeasurements[] (type = Kelly Bushing / rotary table, unit m) | LAS ELEV + ELEV_TYPE, PDF | parsed / llm_extracted |
| Total depth MD | VerticalMeasurements[] (type = total depth, path = MD) | PDF ("TD @ 3682 m MD RKB") | llm_extracted |
| Kick-off point | VerticalMeasurements[] (type = kick-off point, path = MD) | PDF ("KOP @ 2620 m MD RKB") | llm_extracted |
| Surface location | Well SpatialLocation (lat/lon; record CRS) | LAS LAT/LON (+ XCOORD/YCOORD) | parsed |
| Field | GeoContexts[] -> Field "VOLVE" | LAS FLD | parsed |
| Operator | CurrentOperatorID -> Organisation ref | LAS COMP ("STATOILHYDRO") | LLM normalizes |
| Log depth range | WellLog TopMeasuredDepth / BottomMeasuredDepth, SamplingStart/Stop, SamplingInterval | LAS STRT/STOP/STEP | parsed |
| Null value | WellLog NullValue | LAS NULL | parsed |
| Curves | Curves[]: Mnemonic, CurveUnit, LogCurveTypeID, CurveDescription, TopDepth/BaseDepth, DepthUnit | LAS ~Curve section | parsed + LLM maps type/unit |
| Trajectory | WellboreTrajectory depths + AvailableTrajectoryStationProperties; stations -> Parquet | well path file | parsed |

Open questions for Claude Code to resolve and document in `docs/architecture.md`:

- The exact VerticalMeasurementTypeID and VerticalMeasurementPathID reference values for KB, TD and KOP.
- The CRS of LAS LAT/LON. NPD lists geodatum ED50 for these wells. Record the CRS assumption explicitly and flag it.
- ID convention: `volve:master-data--Wellbore:NO-15-9-F-12:` (namespace configurable). It must match the schema pattern.
- ACL/legal are placeholders, as in Equinor's own samples/author_welllog.py.

## 6. Architecture

### 6.1 Pipeline

```
bundle (LAS/DLIS, well path, PDF)
   │
   ▼
[1 inventory] ─ deterministic: list files, sniff type, plan vs actual well path
   ▼
[2 resolve_identity] ─ LLM + rules: canonical wellbore, parent well, sidetrack relation
   ▼
[3 extract_facts] ─ parsed facts from LAS/well path + LLM facts from PDF (value + quote + page)
   ▼
[4 map_curves] ─ LLM with tool lookup_reference(kind, query) -> UoM + LogCurveType IDs + confidence
   ▼
[5 reconcile] ─ deterministic: same fact from several sources -> agree / conflict (tolerances)
   ▼
[6 build_records] ─ deterministic: osdu-python-models -> records + Parquet bulk + manifest
   ▼
[7 validate] ─ jsonschema + Pydantic + rules + provenance + grounding
   │      └─ on failure: route error back to node 3/4 (max 2 retries), else flag
   ▼
[8 report] ─ outputs/<run_id>/<wellbore>/ manifest.json, records/*.json, bulk/*.parquet,
             provenance.json, review.md, trace.jsonl (every LLM call, tokens, latency)
```

### 6.2 LangGraph

- State (Pydantic): wellbore, files, facts: list[Fact], curve_mappings, records, validation: list[Issue], flags: list[ReviewFlag], attempts, cost.
- Nodes = steps 1-8. Conditional edge after validate.
- Tools exposed to the LLM: `read_las_header(file)`, `list_curves(file)`, `search_pdf(file, query)` (returns page + text spans), `lookup_reference(kind, query, top_k)`, `get_schema_field(kind, path)`.
- The LLM only returns structured JSON validated by Pydantic. On a schema error, retry once with the error message.

### 6.3 Core data types

```python
class Provenance(BaseModel):
    source_file: str
    locator: str  # e.g. "LAS:~Well/ELEV", "PDF:p7", "WELLPATH:row 0"
    method: Literal["parsed", "llm_extracted", "derived"]
    quote: str | None = None  # required for llm_extracted
    model: str | None = None
    prompt_version: str | None = None


class Fact(BaseModel):
    name: str  # "kb_elevation_m", "td_md_m", "kop_md_m", ...
    value: float | str | None
    unit: str | None
    provenance: list[Provenance]
    confidence: float | None = None


class ReviewFlag(BaseModel):
    severity: Literal["info", "warn", "block"]
    fact: str
    reason: str  # "conflict", "ungrounded", "plan_not_actual", "unit_assumed", ...
    candidates: list[Fact]
```

### 6.4 LLM provider

- Use an OpenAI-compatible client with env vars `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.
- Default: GitHub Models free tier, with a personal GitHub token (it runs on Azure AI, which relates to the Azure AI Foundry nice-to-have). Claude Code: verify the current endpoint, model names and rate limits in GitHub's docs before coding. Don't hardcode them.
- Optional local fallback for offline tests: Ollama with a small model (laptop GPU is 4 GB). Expect lower quality.
- Disk cache all calls (`.cache/llm/`, gitignored). Evals must be re-runnable from cache.

## 7. Validation rules (src/volve_osdu/validate/)

1. Schema: jsonschema for each record against the pinned schema, plus Pydantic model_validate.
2. IDs: match the schema pattern; every referenced ID exists in the manifest or reference list.
3. Reference values: UoM, LogCurveType and VerticalMeasurementType IDs exist in the pinned reference lists.
4. Depth logic: Top < Bottom; KOP < TD; trajectory MD increasing; TVD <= MD. A log curve with non-null samples deeper than TD or the last actual survey station (+5 m) raises a warn flag naming the curve, the depth range and both sources (see the F-12 GR case in 4.2).
5. Units: depth in metres; if the source is in feet, convert and add an info flag.
6. Geography: lat/lon inside the Volve box (58.40-58.50 N, 1.80-1.95 E), else block.
7. Provenance: every non-null field has >= 1 provenance entry.
8. Grounding: llm_extracted facts must have a quote found in the source text (whitespace normalized) with the value inside the quote; otherwise drop the value and raise a warn.
9. Consistency: multi-source facts within tolerance (depth 0.5 m, elevation 0.2 m, lat/lon 1e-4 deg); otherwise a conflict flag with all candidates.
10. Plans: a well path file whose name contains PLAN/PROTOTYPE/rev is never the definitive trajectory.

## 8. Evaluation (src/volve_osdu/eval/)

### 8.1 Systems compared

- **rules**: deterministic parsers + regex on PDF text + static mnemonic dictionary. No LLM.
- **llm_only**: one prompt per wellbore with all extracted text; the LLM returns the OSDU data JSON directly. Same validators and scoring afterwards.
- **agent**: the full graph from section 6.
- Ablation (if time): agent without the validate -> retry loop.

### 8.2 Metrics (per system, per field, overall)

| Metric | Definition |
|---|---|
| Field accuracy | correct / total over recoverable gold fields; tolerances: depth 0.5 m, elevation 0.2 m, lat/lon 1e-4 deg, strings normalized |
| Abstention accuracy | share of non-recoverable fields correctly left null |
| Curve mapping accuracy | exact match of UoM ID and of LogCurveType ID vs reviewed gold labels |
| Grounding rate | share of llm_extracted facts passing the grounding check |
| Hallucination rate | share of populated fields with no valid provenance, or a value absent from all sources |
| Validation pass rate | records passing all rules on the first attempt, and after retries |
| Review-flag precision/recall | flags vs conflicts.csv (known + injected conflicts) |
| Marker P/R (stretch) | matched tops (normalized name, MD within 1 m) vs Well_picks |
| Cost, latency | tokens and seconds per wellbore (from trace) |

### 8.3 Statistics and honesty

- Bootstrap over wellbores (2,000 resamples, 95% percentile CI). n is small (13 MVP wellbores), so always show CIs and n. Never claim significance without them.
- Report per-field tables, not only averages. Show the worst failures with examples.
- Report the share of gold labels reviewed by a human.
- Freeze prompts and the model version for the reported run; record them in docs/results.md.

### 8.4 Output

`uv run volve-osdu eval` writes `docs/results.md`:

- a summary table (systems x metrics, with CIs)
- per-field accuracy
- the top 5 error cases with source excerpts
- cost/latency
- the exact run config (model, prompt versions, data commits, date)

## 9. Milestones

Dates assume evenings plus the weekend. Each milestone ends with tests green, a short summary, and a stop for review.

### M0 - Setup and data (Thu 5 - Fri 6 Nov)

- Repo skeleton (section 10 layout), pyproject.toml, .env.example, ruff, pytest, CI (GitHub Actions: lint + tests, no LLM calls).
- `scripts/download_data.sh`: clone the pinned commits into data/raw/; fetch the pinned reference values.
- `configs/wells.yaml`: the 13 MVP bundles (folder -> canonical name -> files), well path mapping.
- `scripts/build_gold.py`: build wellbore_headers.csv from NPD files, parse Well_picks_Volve_v1.dat.
- Accept when data downloads from scratch in one command, gold builds, and wells.yaml matches the files on disk (a test checks this).

### M1 - Deterministic golden path for 15/9-F-12 (Sat 7 - Sun 8 Nov)

- Readers: LAS (lasio), well path, PDF text with page numbers (pdfplumber).
- Builders: Well, Wellbore, WellLog (+ Parquet), WellboreTrajectory, Manifest with osdu-python-models.
- Validators: rules 1-7, 9, 10.
- `volve-osdu run --wellbore "15/9-F-12" --system rules` writes the full output.
- Accept when F-12 produces a valid manifest, review.md shows the GR-below-final-survey warn flag (4.2), the plan/prototype well paths are excluded, and there are unit tests for every reader and rule.

### M2 - Agent (Mon 9 - Tue 10 Nov)

- LLM client + disk cache + trace. Prompts v1 in agent/prompts/.
- Nodes 2 (identity), 3 (PDF facts with quotes), 4 (curve mapping with lookup_reference), the validate -> retry edge, and rule 8 (grounding).
- Run on all 13 MVP wellbores.
- Accept when all 13 run end to end, every llm_extracted fact has a quote, the cache works (a second run makes 0 API calls), and the trace logs tokens and latency.

### M3 - Evaluation (Wed 11 Nov)

- Owner reviews curve_labels.csv (Claude Code drafts it; owner marks reviewed).
- conflicts.csv: known conflicts plus 10-20 injected perturbations.
- Baselines rules and llm_only; metrics; bootstrap; docs/results.md.
- Accept when one command reproduces the results from cache and the numbers in the README come from docs/results.md.

### M4 - Packaging (Thu 12 Nov)

- README (section 10.2), docs/architecture.md with a diagram (Mermaid), limitations section, attribution.
- Demo: a static HTML report for one wellbore (inputs -> records -> flags) or a short GIF of the CLI.
- Accept when a fresh clone, following the README, runs the demo wellbore in under 10 minutes.

### M5 - Publish (Fri 13 Nov)

- Public repo under wgKaminari, tagged v0.1.0, topics: osdu, volve, langgraph, agentic-ai, llm-evaluation.
- Announce the release.
- Buffer Sat 14 - Tue 17 Nov for fixes and stretch items. Don't start stretch items before M5.

## 10. Repository and deliverables

### 10.1 Layout

```
volve-osdu-agent/
├── CLAUDE.md
├── README.md
├── LICENSE                     # Apache-2.0 for code (matches Equinor OSDU repos)
├── pyproject.toml / uv.lock
├── .env.example                # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, OSDU_NAMESPACE
├── .github/workflows/ci.yml
├── configs/ wells.yaml settings.yaml
├── scripts/ download_data.sh build_gold.py
├── data/                       # raw/ (gitignored), gold/ (committed, small, attributed)
├── src/volve_osdu/ ingest/ osdu/ validate/ agent/ eval/ cli.py
├── tests/ fixtures/ test_*.py
├── outputs/                    # gitignored, except one committed example run for F-12
└── docs/ PROJECT_GUIDE.md architecture.md results.md
```

### 10.2 README outline

- One-line pitch + headline numbers (from results.md)
- The problem (3 sentences: manual OSDU migration)
- Demo: F-12 before -> after, with the review flag example
- How it works (diagram + "LLM proposes, code computes, validators judge")
- Results table with CIs vs baselines
- Quickstart (5 commands)
- Design decisions (provenance, grounding, abstention, human review)
- Limitations and responsible-AI notes (small n, placeholder ACL/legal, CRS assumption, no real OSDU instance)
- Data attribution (Equinor Volve licence, NPD/Sodir) and credits (osdu-python-models, lasio, dlisio, spwla_volve, Volve_field_data)

## 11. Prompts to drive Claude Code

Paste one at a time and review after each.

**Kickoff**

> Read CLAUDE.md and docs/PROJECT_GUIDE.md fully. Then give me: (1) your understanding of the project in 5 bullets, (2) any contradictions or risks you see in the guide, (3) a task list for Milestone 0 only. Don't write code yet.

**Per milestone**

> Implement Milestone <N> from docs/PROJECT_GUIDE.md. Follow CLAUDE.md rules. Write tests first for readers and validators. When done: run ruff and pytest, show the results, summarize what you built, list open questions, and stop.

**Review gate**

> Before we continue: show me 5 random facts from the last run with their provenance, and check that each one is actually in the source file. Report any mismatch.

**Evaluation sanity**

> Audit the evaluation for leakage: prove the agent and baselines never open data/gold, NPD files or Well_picks. Show the file-access trace for one run.

## 12. Communication

Notes on announcing and sharing the project are kept outside this repository.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| OSDU semantics unclear (reference types, CRS) | Document assumptions in architecture.md; flag them in output; ask the owner |
| Free LLM rate limits | Disk cache, small prompts, batch curve mapping per file |
| Small n -> wide CIs | Show CIs honestly; per-field tables; add DLIS wellbores if time |
| Gold label bias (AI-drafted) | Owner review required; report the reviewed share |
| Scope creep | MVP first; stretch only after M5 |
| Licence concerns | Don't commit raw data; attribution section; no commercial use |
| Limited time (evenings only) | Milestones sized for evenings; buffer Nov 14-17 |

## 14. Glossary

- **MD** measured depth (along the hole) · **TVD** true vertical depth · **TVDSS** TVD below sea level
- **KB / RKB** kelly bushing / rotary kelly bushing: the depth reference point on the rig floor
- **TD** total depth · **KOP** kick-off point, where a sidetrack leaves the parent hole
- **Sidetrack** a new wellbore drilled from an existing one (suffix A, B, T2)
- **Mnemonic** short curve code in a log file (GR, PHIF, SW, VSH)
- **Formation top / marker / pick** depth where a geological unit starts
- **WPC** work-product-component (OSDU) · **Manifest** OSDU ingestion bundle
- **Reference data** OSDU controlled vocabularies (units, curve types, measurement types)
- **Provenance** where a value came from · **Grounding** proof that an AI-extracted value is in the source

## 15. Links

- Equinor OSDU Python models: https://github.com/equinor/osdu-python-models
- Equinor OSDU MCP PoC: https://github.com/equinor/osdu-mcp-poc
- Volve data sharing: https://www.equinor.com/energy/volve-data-sharing
- spwla_volve: https://github.com/andymcdgeo/spwla_volve
- Volve_field_data: https://github.com/awgeo/Volve_field_data
- OSDU data definitions: https://community.opengroup.org/osdu/data/data-definitions
- lasio: https://github.com/kinverarity1/lasio · dlisio: https://github.com/equinor/dlisio
- LangGraph: https://github.com/langchain-ai/langgraph
