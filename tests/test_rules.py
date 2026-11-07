"""Tests for business rules 2-7 and 10, each with a small failing and passing case."""

import pandas as pd
import pytest

from conftest import FIXTURES, parsed
from volve_osdu.ingest.las import LasLog
from volve_osdu.ingest.wellpath import WellPath
from volve_osdu.osdu.records import Record
from volve_osdu.validate import rules

REFERENCE = FIXTURES.parent.parent / "data" / "raw" / "reference"


def short_path(base_md: float, name: str = "F-12_ACTUAL") -> WellPath:
    stations = pd.DataFrame({"md_m": [100.0, base_md], "tvd_m": [100.0, base_md - 50]})
    return WellPath(path=FIXTURES / name, is_plan="PLAN" in name, stations=stations)


def test_rule2_flags_dangling_references(records: list[Record]) -> None:
    assert rules.rule2_references(records) == []
    without_well = [r for r in records if r.type != "Well"]
    issues = rules.rule2_references(without_well)
    assert {i.path for i in issues} == {"WellID"}
    assert issues[0].severity == "error"


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference data not downloaded")
def test_rule3_catches_invented_reference_values(records: list[Record]) -> None:
    assert rules.rule3_reference_values(records, "volve") == []
    log = next(r for r in records if r.type == "WellLog")
    log.data["Curves"][0]["LogCurveFamilyID"] = "volve:reference-data--LogCurveFamily:GammaRay:"
    issues = rules.rule3_reference_values(records, "volve")
    assert len(issues) == 1 and issues[0].severity == "error"


def test_rule4_log_below_final_survey_is_flagged_with_both_sources(
    records: list[Record], las: LasLog
) -> None:
    # Fixture GR goes to 3500.6 m; a well path ending at 3490 m is > 5 m shallower.
    _, flags = rules.rule4_depths(records, [(las, 1.0)], short_path(3490.0), {})
    gr = [f for f in flags if f.fact == "GR_base_md_m"]
    assert len(gr) == 1 and gr[0].reason == "log_below_survey"
    assert {c.name for c in gr[0].candidates} == {"GR_base_md_m", "final_survey_md_m"}


def test_rule4_within_tolerance_is_not_flagged(records: list[Record], las: LasLog) -> None:
    _, flags = rules.rule4_depths(records, [(las, 1.0)], short_path(3497.0), {})
    assert flags == []


def test_rule4_kop_below_td_and_bad_well_path(records: list[Record]) -> None:
    facts = {"kop_md_m": parsed("kop_md_m", 3600.0), "td_md_m": parsed("td_md_m", 3500.0)}
    bad = WellPath(
        FIXTURES / "x", False, pd.DataFrame({"md_m": [100.0, 90.0], "tvd_m": [100.0, 95.0]})
    )
    issues, flags = rules.rule4_depths(records, [], bad, facts)
    assert any(f.reason == "kop_not_above_td" for f in flags)
    assert any("not strictly increasing" in i.message for i in issues)
    assert any("TVD > MD" in i.message for i in issues)


def test_rule5_depth_unit_must_be_metres(records: list[Record]) -> None:
    assert [i for i in rules.rule5_units(records, "volve") if i.severity == "error"] == []
    log = next(r for r in records if r.type == "WellLog")
    log.data["Curves"][0]["DepthUnit"] = "volve:reference-data--UnitOfMeasure:ft:"
    assert any(i.severity == "error" for i in rules.rule5_units(records, "volve"))


def test_rule6_location_outside_volve_blocks() -> None:
    inside = {
        "surface_latitude_deg": parsed("lat", 58.44),
        "surface_longitude_deg": parsed("lon", 1.89),
    }
    swapped = {
        "surface_latitude_deg": parsed("lat", 1.89),
        "surface_longitude_deg": parsed("lon", 58.44),
    }
    assert rules.rule6_geography(inside) == []
    assert rules.rule6_geography(swapped)[0].severity == "block"


def test_rule7_every_value_needs_provenance(records: list[Record]) -> None:
    assert rules.rule7_provenance(records) == []
    well = next(r for r in records if r.type == "Well")
    well.data["FacilityDescription"] = "typed by hand"
    issues = rules.rule7_provenance(records)
    assert [i.path for i in issues] == ["FacilityDescription"]


def test_rule10_plan_is_never_the_trajectory() -> None:
    assert rules.rule10_plans(short_path(3520.0)) == []
    flags = rules.rule10_plans(short_path(3520.0, "F-9A Utsira Water injector Rev10 PLAN"))
    assert flags[0].reason == "plan_not_actual" and flags[0].severity == "block"
