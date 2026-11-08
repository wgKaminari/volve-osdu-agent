# Review: 15/9-F-12

System: `agent` · Records: 10 · Review flags: 6 · Validation errors: 0

**Status: ready to ingest after review**

## Review flags

| Severity | Fact | Reason | Details | Sources |
|---|---|---|---|---|
| warn | td_md_m | ungrounded | dropped LLM value 3500.0: quote does not state a total depth | 3500.0 ← data/raw/spwla_volve/15_9-F12/PETROPHYSICAL_REPORT_1.PDF (PDF:p5) |
| warn | kop_md_m | ungrounded | dropped LLM value 0.0: no quote | 0.0 ← data/raw/spwla_volve/15_9-F12/PETROPHYSICAL_REPORT_1.PDF (PDF:p0) |
| warn | kickoff_wellbore_name | ungrounded | dropped LLM value '15/9-F-12': no quote | 15/9-F-12 ← data/raw/spwla_volve/15_9-F12/PETROPHYSICAL_REPORT_1.PDF (PDF:p0) |
| warn | kb_elevation_m | ungrounded | dropped LLM value 0.0: no quote | 0.0 ← data/raw/spwla_volve/15_9-F12/PETROPHYSICAL_REPORT_1.PDF (PDF:p0) |
| warn | surface_location | crs_assumed | LAS LAT/LON state no datum; recorded as ED50 (EPSG:4230). Confirm the datum before ingestion (an ED50/WGS84 mix-up moves the well ~100 m). | 58.441713 ← data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/LAT); 58.441713 ← data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/LAT); 1.88748 ← data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/LON); 1.88748 ← data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/LON) |
| warn | GR_base_md_m | log_below_survey | WLC_PETRO_COMPUTED_INPUT_1.LAS curve GR has data down to 4186.7 m MD, 666.7 m below the final survey station at 3520.0 m MD (4,375 non-null samples deeper) | 4186.7328 ← data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Curve/GR last non-null sample); 3520.0 ← data/raw/volve_field_data/input_data/wellpaths/F-12_ACTUAL (WELLPATH:MD row 210) |

## Facts used

| Fact | Value | Sources |
|---|---|---|
| field_name | VOLVE | data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/FLD); data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/FLD) |
| kb_elevation_m | 54.9 m | data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/ELEV); data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/ELEV) |
| operator_name | STATOILHYDRO | data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/COMP); data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/COMP) |
| surface_latitude_deg | 58.441713 deg | data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/LAT); data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/LAT) |
| surface_longitude_deg | 1.88748 deg | data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS (LAS:~Well/LON); data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS (LAS:~Well/LON) |

## Records

- `osdu:wks:master-data--Organisation:1.2.0` `volve:master-data--Organisation:STATOILHYDRO`
- `osdu:wks:master-data--Field:1.1.0` `volve:master-data--Field:VOLVE`
- `osdu:wks:master-data--Well:1.5.0` `volve:master-data--Well:NO-15-9-F-12`
- `osdu:wks:dataset--File.Generic:1.0.0` `volve:dataset--File.Generic:NO-15-9-F-12-trajectory`
- `osdu:wks:work-product-component--WellboreTrajectory:1.4.0` `volve:work-product-component--WellboreTrajectory:NO-15-9-F-12-F-12_ACTUAL`
- `osdu:wks:master-data--Wellbore:1.5.1` `volve:master-data--Wellbore:NO-15-9-F-12`
- `osdu:wks:dataset--File.Generic:1.0.0` `volve:dataset--File.Generic:NO-15-9-F-12-WLC_PETRO_COMPUTED_INPUT_1`
- `osdu:wks:work-product-component--WellLog:1.5.0` `volve:work-product-component--WellLog:NO-15-9-F-12-WLC_PETRO_COMPUTED_INPUT_1`
- `osdu:wks:dataset--File.Generic:1.0.0` `volve:dataset--File.Generic:NO-15-9-F-12-WLC_PETRO_COMPUTED_OUTPUT_1`
- `osdu:wks:work-product-component--WellLog:1.5.0` `volve:work-product-component--WellLog:NO-15-9-F-12-WLC_PETRO_COMPUTED_OUTPUT_1`

## Inputs

- LAS: `data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_INPUT_1.LAS`
- LAS: `data/raw/spwla_volve/15_9-F12/WLC_PETRO_COMPUTED_OUTPUT_1.LAS`
- PDF: `data/raw/spwla_volve/15_9-F12/PETROPHYSICAL_REPORT_1.PDF`, 5 pages (image-heavy: few facts can be read as text)
- Well path: `data/raw/volve_field_data/input_data/wellpaths/F-12_ACTUAL` (actual)
- Plan/prototype well paths in the folder, never used: `F-10 A rev#6 PROTOTYPE`, `F-9A Utsira Water injector Rev10 PLAN`

## Validation

All checks passed (rules 1-7, 9, 10).

10 info notes (e.g. curves left unmapped) are in validation.json.
