# Architecture notes

Working document. Records design decisions and the answers to the open questions in
`PROJECT_GUIDE.md` section 5.2. Status: draft after Milestone 0 (2026-11-05).

## Data sources and pins

| What | Where (after `scripts/download_data.sh`) | Pin |
|---|---|---|
| LAS/DLIS logs, petrophysical PDFs, Well_picks | `data/raw/spwla_volve/` | `c293edf37c1b567b8dc9c81ea88f2cf288eab423` |
| Well paths, NPD headers | `data/raw/volve_field_data/input_data/` | `7cdecf1f1d24811d21bb2e2f379ff048404f4ce7` |
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

Open: the path list has both `MeasuredDepth` and `MD` (same meaning). Pick one in M1 and use it
consistently; proposal `MeasuredDepth` (the longer, descriptive form).

### CRS of LAS LAT/LON
NPD lists geodatum ED50 for these wellbores. The F-12 LAS LAT/LON (58.441713, 1.887480) matches the
NPD values (58.441714, 1.887481) within 1e-6 deg, so LAS coordinates are taken as **ED50**:
`reference-data--CoordinateReferenceSystem:Geographic2D:EPSG::4230`. The assumption is recorded in
every Well record and stated in the README limitations.

### ID convention
`<namespace>:master-data--Wellbore:NO-15-9-F-12:` style, namespace from settings. To confirm against
the schema `pattern` in M1.

### ACL / legal
Placeholders, as in Equinor's `osdu-python-models` samples. To be filled in M1.

## Findings that affect later milestones

- **Ground-truth coverage:** NPD has no header for 15/9-19 BT2 or 15/9-F-11 T2 (technical sidetracks
  are not registered separately), so header accuracy is scored on 11 wellbores. Well_picks cover all 13.
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
  while record schemas are M27.1 (v0.30.1). Check in M1 that its `$ref`s resolve.
