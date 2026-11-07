"""Tests for wellbore name normalization."""

import pytest

from volve_osdu.extract.names import normalize_wellbore_name, short_to_full, well_name_of


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("15/9-F-12", "15/9-F-12"),
        ("NO 15/9-F-12", "15/9-F-12"),
        ("NO_15/9-19_A", "15/9-19 A"),
        ("NO 15/9-19 BT2", "15/9-19 BT2"),
        ("15/9-F-11 T2", "15/9-F-11 T2"),
        ("UNKNOWN", None),
    ],
)
def test_normalize_wellbore_name(raw: str, name: str | None) -> None:
    assert normalize_wellbore_name(raw) == name


@pytest.mark.parametrize(
    ("wellbore", "well"),
    [("15/9-F-1 A", "15/9-F-1"), ("15/9-19 BT2", "15/9-19"), ("15/9-F-12", "15/9-F-12")],
)
def test_sidetracks_share_parent_well(wellbore: str, well: str) -> None:
    assert well_name_of(wellbore) == well


def test_short_names_from_report_prose() -> None:
    assert short_to_full("F-11 T2") == "15/9-F-11 T2"
    assert short_to_full("15/9-F-1") == "15/9-F-1"
