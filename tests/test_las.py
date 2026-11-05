"""Tests for the LAS reader, using a tiny fixture in the same layout as the Volve WLC files."""

import math
from pathlib import Path

from volve_osdu.ingest.las import read_las

SAMPLE = Path(__file__).parent / "fixtures" / "sample.las"


def test_header_values() -> None:
    log = read_las(SAMPLE)
    assert log.header_value("WELL") == "15/9-F-12"
    assert log.header_value("COMP") == "STATOILHYDRO"
    assert log.header_value("ELEV") == 54.9
    assert log.well["ELEV"].unit == "M"
    assert log.header_value("NULL") == -999.25
    assert log.header_value("MISSING") is None


def test_depth_and_curves() -> None:
    log = read_las(SAMPLE)
    assert log.depth_unit == "M"
    assert [c.mnemonic for c in log.curves] == ["GR", "RHOB"]
    assert log.data.index[0] == 3500.0


def test_curve_description_keeps_colons() -> None:
    gr = read_las(SAMPLE).curves[0]
    assert gr.unit == "API"
    assert gr.description == "GR:UNKNOWN:rC:NONE:v1"


def test_null_values_become_nan_and_valid_range_is_computed() -> None:
    log = read_las(SAMPLE)
    gr, rhob = log.curves
    assert math.isnan(log.data["RHOB"].iloc[-1])
    assert gr.n_valid == 5
    assert gr.base_depth == 3500.6096
    assert rhob.n_valid == 2
    assert rhob.base_depth == 3500.1524
