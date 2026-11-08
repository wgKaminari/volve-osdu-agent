"""Tests for evaluation code: scoring rules, bootstrap, perturbation edits, flag matching."""

from pathlib import Path

from conftest import FIXTURES
from volve_osdu.eval.conflicts import detections
from volve_osdu.eval.metrics import Outcome, per_wellbore, ratio_with_ci, same
from volve_osdu.eval.perturb import delete_header, depth_to_feet, set_header
from volve_osdu.eval.predictions import _code
from volve_osdu.ingest.las import read_las

SAMPLE = (FIXTURES / "sample.las").read_text()


def test_same_uses_tolerances_and_operator_aliases() -> None:
    assert same("td_md_m", 3632.4, "3632.0")
    assert not same("td_md_m", 3633.0, "3632.0")
    assert same("kb_elevation_m", 54.9, "54.9") and not same("kb_elevation_m", 54.9, "54.0")
    assert same("operator", "STATOILHYDRO", "Statoil ASA (old)")
    assert same("operator", "STATOIL PETROLEUM AS", "Den norske stats oljeselskap a.s")
    assert not same("operator", "Norsk Hydro", "Statoil Petroleum AS")
    assert not same("operator", "STATOIL PETRPOLEUM AS", "Statoil Petroleum AS")  # typo stays wrong
    assert not same("field", None, "VOLVE")


def test_bootstrap_ci_contains_pooled_ratio() -> None:
    est = ratio_with_ci({"a": (9, 10), "b": (5, 10), "c": (10, 10)})
    assert est.value == 24 / 30
    assert est.low is not None and est.high is not None
    assert est.low <= est.value <= est.high
    assert ratio_with_ci({}).value is None


def test_per_wellbore_skips_disputed_rows() -> None:
    outcomes = [
        Outcome("w1", "td_md_m", "field", "1", 1.0, True),
        Outcome("w1", "kop_md_m", "disputed", "2", 3.0, None),
        Outcome("w2", "td_md_m", "field", "1", 9.0, False),
    ]
    assert per_wellbore(outcomes, "field") == {"w1": (1, 1), "w2": (0, 1)}


def test_reference_codes_are_decoded() -> None:
    assert _code("volve:reference-data--LogCurveFamily:Gamma%20Ray:") == "Gamma Ray"
    assert _code("volve:reference-data--UnitOfMeasure:m3%2Fm3:") == "m3/m3"
    assert _code(None) is None


def test_las_header_edits_round_trip_through_lasio(tmp_path: Path) -> None:
    edited = set_header(delete_header(SAMPLE, "ELEV_TYPE"), "FLD", "SLEIPNER")
    edited = set_header(edited, "ELEV", "180.1000", "F")
    path = tmp_path / "x.las"
    path.write_text(edited)
    log = read_las(path)
    assert log.header_value("FLD") == "SLEIPNER"
    assert log.header_value("ELEV") == 180.1 and log.well["ELEV"].unit == "F"
    assert log.header_value("ELEV_TYPE") is None


def test_depth_to_feet_converts_header_curve_unit_and_data(tmp_path: Path) -> None:
    path = tmp_path / "ft.las"
    path.write_text(depth_to_feet(SAMPLE))
    log = read_las(path)
    assert log.depth_unit == "F"
    assert abs(log.data.index[0] - 3500.0 * 3.280839895) < 0.01
    assert abs(float(log.header_value("STRT")) - 11482.94) < 0.01  # type: ignore[arg-type]


def test_detections_collapse_depth_flags_and_ignore_non_conflicts() -> None:
    flags = [
        {"fact": "GR_base_md_m", "reason": "log_below_survey"},
        {"fact": "RHOB_base_md_m", "reason": "log_below_survey"},
        {"fact": "surface_location", "reason": "crs_assumed"},
        {"fact": "kop_md_m", "reason": "ungrounded"},
        {"fact": "kb_elevation_m", "reason": "conflict"},
    ]
    assert detections("P03", flags) == {
        ("P03", "*", "log_below_survey"),
        ("P03", "kb_elevation_m", "conflict"),
    }
