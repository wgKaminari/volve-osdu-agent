# Architecture notes

Working document. Records design decisions and the answers to the open questions in
`PROJECT_GUIDE.md` section 5.2. Status: updated after Milestone 1 (2026-11-07).

## Data sources and pins

| What | Where (after `scripts/download_data.sh`) | Pin |
|---|---|---|
| LAS/DLIS logs, petrophysical PDFs, Well_picks | `data/raw/spwla_volve/` | `c293edf37c1b567b8dc9c81ea88f2cf288eab423` |
| Well paths, NPD headers | `data/raw/volve_field_data/input_data/` | `7cdecf1f1d24811d21bb2e2f379ff048404f4ce7` |
| Record JSON schemas (M27.1, matching the Pydantic models) | `data/raw/osdu-python-models/schemas/M27.1/` | `5213c7cf341806fb3f456f33160cad34839ad586` (tag v0.8.1) |
| Manifest schema | `data/raw/osdu-mcp-poc/schemas/manifest/` | `b2a648d68b12c60848098636dcbce621cf4e9277` (main, 2026-11-01) |
| OSDU reference values | `data/raw/reference/` | data-definitions tag `v0.30.1` = `ff89d87caa43d05d1341dcaa6d258e1186ec8aa6` |

Reference-value files fetched (from `ReferenceValues/Manifests/reference-data/`):

| File | Governance | Entries |
|---|---|---|
| `OPEN/UnitOfMeasure.1.json` | OPEN | 1,451 |
| `OPEN/VerticalMeasurementType.1.json` | OPEN | 58 |
| `OPEN/VerticalMeasurementPath.1.json` | OPEN | 6 |
| `LOCAL/LogCurveType.1.json` | LOCAL | 42,919 |
| `LOCAL/LogCurveFamily.1.json` | LOCAL | 2,198 |
| `LOCAL/CoordinateReferenceSystem.1.json` | LOCAL | 2,547 |

All reference IDs in these files start with the placeholder `{{NAMESPACE}}:`. Our code substitutes
the namespace from `OSDU_NAMESPACE` (see `.env.example`).

## Input vs gold separation (leakage)

Inputs and gold live in the same downloaded repos, so the boundary is by path, not by repo:

- Agent inputs: the files listed in `configs/wells.yaml` (LAS, PDF, well path) and nothing else.
- Gold only: `volve_field_data/input_data/wellheaders/*`, `spwla_volve/Well_picks_Volve_v1.dat`,
  `data/gold/*`. Read only by `src/volve_osdu/eval/` and `scripts/build_gold.py`.
- Not used by anyone: `spwla_volve/VOLVE_INVENTORY.xlsx`, `volve_field_data/input_data/lithostrat/*`.

## Resolved questions (guide section 5.2)

### Vertical measurement reference values
Present in data-definitions v0.30.1:

| Fact | VerticalMeasurementTypeID | VerticalMeasurementPathID |
|---|---|---|
| KB / RKB elevation | `reference-data--VerticalMeasurementType:KellyBushing` (alt. `RotaryTable`) | `reference-data--VerticalMeasurementPath:ELEV` |
| Total depth | `reference-data--VerticalMeasurementType:TotalDepth` | `reference-data--VerticalMeasurementPath:MeasuredDepth` |
| Kick-off point | `reference-data--VerticalMeasurementType:KickOffPoint` | `reference-data--VerticalMeasurementPath:MeasuredDepth` |

The path list has both `MeasuredDepth` and `MD` (same meaning). Decided in M1: `MeasuredDepth`
everywhere. TD and KOP carry `VerticalReferenceID: "KB"` because the reports quote "m MD RKB".

### CRS of LAS LAT/LON
NPD lists geodatum ED50 for these wellbores. The F-12 LAS LAT/LON (58.441713, 1.887480) matches the
NPD values (58.441714, 1.887481) within 1e-6 deg, so LAS coordinates are taken as **ED50**:
`reference-data--CoordinateReferenceSystem:Geographic2D:EPSG::4230`. The assumption is recorded in
every Well record and stated in the README limitations.

### ID convention
Record IDs `<namespace>:master-data--Wellbore:NO-15-9-F-12` (no version); references to them add a
trailing `:` (latest version). Confirmed against the M27.1 schema patterns in `tests/test_ids.py`.
WellLog/trajectory IDs append the source file stem (`...:NO-15-9-F-12-WLC_PETRO_COMPUTED_INPUT_1`).

### ACL / legal
Placeholders, as in Equinor's samples: owners/viewers `data.default.{owners,viewers}@volve.example.com`
(the ACL schema requires e-mail form), legal tag `volve-equinor-open-data-licence`, country `NO`.

## Pipeline as built in M1

`volve-osdu run --wellbore "15/9-F-12" --system rules` (`src/volve_osdu/pipeline.py`):

1. Inventory: read the bundle's LAS, PDF and well path (missing files become issues).
2. Parsed facts from LAS headers (WELL/UWI, ELEV+ELEV_TYPE, LAT/LON, FLD, COMP).
3. The *system* decides the judgement steps (`Judgement`): wellbore name, facts from report prose,
   curve mappings. `rules` = most specific LAS name, regex on PDF prose (`extract/pdf_rules.py`),
   static curve dictionary (`extract/curves.py`). M2 adds `agent` with the same interface.
4. Reconcile (rule 9): agreeing values merge their sources; disagreeing values give a `conflict`
   flag with every candidate. Majority wins; on a tie the field is left empty.
5. Records: Organisation, Field, Well, Wellbore, WellLog per LAS, WellboreTrajectory, one
   `dataset--File.Generic` per Parquet bulk file. Data blocks go through Equinor's Pydantic models.
6. Validation: rule 1 (jsonschema against pinned M27.1, manifest against osdu-mcp-poc), 2-7, 10.
7. Outputs in `outputs/<run_id>/<folder>/`: manifest.json, records/, bulk/*.parquet,
   provenance.json (per record, per JSON path), facts.json, validation.json, review.md.

Decisions made in M1:

- Organisation and Field are emitted as master-data records so that `CurrentOperatorID` and
  `GeoContexts[].FieldID` resolve inside the manifest (rule 2). The operator name is kept exactly
  as the source writes it (e.g. "STATOILHYDRO"); normalizing it to one company is a judgement step.
- No `work-product--WorkProduct`: the M27.1 schema set has no WorkProduct schema. The manifest
  carries MasterData, WorkProductComponents and Datasets only (all valid without it).
- Well location: only `AsIngestedCoordinates` in ED50 with the CRS's PersistableReference from the
  pinned reference list. `Wgs84Coordinates` is left empty: it needs a datum transformation (pyproj),
  which we don't compute.
- Trajectory: `ProjectedCRSID` is left empty (the X/Y CRS of the well path files is not stated);
  X/Y stay in the Parquet file. Station property types are not set (no pinned
  TrajectoryStationPropertyType list); names and units are.
- Rule 4 compares each curve's deepest non-null sample with the last actual survey station and with
  TD (when known), tolerance 5 m. For 15/9-F-12 it flags GR (4186.7 m vs 3520.0 m, 4,375 samples).
- Rule 2 reports a `KickOffWellbore` pointing to a parent wellbore outside the manifest as info
  (the parent is loaded with its own manifest), every other dangling reference as an error.

## Findings that affect later milestones

- **Ground-truth coverage:** NPD has no header for 15/9-19 BT2 or 15/9-F-11 T2 (technical sidetracks
  are not registered separately), so header accuracy is scored on 11 wellbores. Well_picks cover all 13.
- **15/9-F-11 vs F-11 T2:** the F-11 well path and LAS stop at ~347 m MD, while NPD gives F-11 a TD of
  4562 m. The technical sidetrack F-11 T2 (not registered at NPD) ends at exactly 4562 m. So NPD's
  "15/9-F-11" record describes the hole that was finally drilled, i.e. T2. F-11 header gold (TD, maybe
  more) must be marked disputed; to handle in M3.
- **LogCurveType IDs are vendor-specific** (e.g. `LogCurveType:Schlumberger:GR`). The generic concept
  is `LogCurveFamily` (e.g. "Gamma Ray"). Open decision for M2/M3: map curves to LogCurveFamily as the
  main target and fill LogCurveType only when the vendor is known (proposed).
- **Operator names differ over time:** NPD says "Statoil Petroleum AS", "Statoil ASA (old)" or
  "Den norske stats oljeselskap a.s"; LAS files say "STATOILHYDRO". Open decision for M3: score with a
  documented alias list (proposed) or strictly.
- **Reports:** 15/9-19 SR has a PDF report; 15/9-19 A and BT2 have Word .doc reports only (not read in
  the MVP). Some folders hold DLIS info-sheet PDFs (`*_INF_1.PDF`) that are not petrophysical reports.
- **Plan/prototype well paths** (`F-10 A rev#6 PROTOTYPE`, `F-9A ... Rev10 PLAN`) belong to stretch
  wellbores. The plan-exclusion rule is tested on the whole `wellpaths/` folder and on a fixture.
- **Manifest schema version:** osdu-mcp-poc's manifest schema comes from data-definitions v0.29.1,
  while record schemas are M27.1 (v0.30.1). Checked in M1: its `$ref`s resolve inside
  osdu-mcp-poc/schemas, and our manifests validate (each record is also validated against M27.1).
- **Rules baseline on all 13 wellbores (M1 dev run):** every manifest is valid. Real source conflicts
  found: 15/9-19 SR field "VOLVE" vs "Q15" and operator "STATOIL PETROLEUM AS" vs "STATOIL" (two LAS
  files); only 15/9-F-12 and the 15/9-19 LFP files carry LAT/LON/ELEV in their LAS headers, so other
  wellbores get KB only from the reports and no surface location (abstained).
