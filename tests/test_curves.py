"""Tests for the static curve dictionary: every entry must exist in the pinned OSDU lists."""

from pathlib import Path

import pytest

from volve_osdu.extract.curves import FAMILIES, UNITS, map_curve
from volve_osdu.osdu.ids import reference_data_id
from volve_osdu.osdu.reference import load_reference_ids

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "raw" / "reference"


def test_map_curve_is_case_insensitive_and_abstains_on_unknowns() -> None:
    gr = map_curve("GR", "API")
    assert (gr.unit_code, gr.family) == ("gAPI", "Gamma Ray")
    assert map_curve("KLOGH", "mD").unit_code == "mD"
    unknown = map_curve("ROP5_RM", "UNKNOWN")
    assert (unknown.unit_code, unknown.family) == (None, None)


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference data not downloaded")
def test_every_dictionary_entry_is_a_real_reference_value() -> None:
    uom = load_reference_ids(REFERENCE / "UnitOfMeasure.1.json", "volve")
    families = load_reference_ids(REFERENCE / "LogCurveFamily.1.json", "volve")
    bad_units = [
        c for c in set(UNITS.values()) if reference_data_id("volve", "UnitOfMeasure", c) not in uom
    ]
    bad_families = [
        f
        for f in set(FAMILIES.values())
        if reference_data_id("volve", "LogCurveFamily", f) not in families
    ]
    assert bad_units == [] and bad_families == []
