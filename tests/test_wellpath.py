"""Tests for the well path reader and the plan/prototype detection."""

from pathlib import Path

import pytest

from volve_osdu.ingest.wellpath import is_plan, read_wellpath

SAMPLE = Path(__file__).parent / "fixtures" / "sample_wellpath.txt"


def test_read_wellpath_columns_and_depths() -> None:
    wp = read_wellpath(SAMPLE)
    assert list(wp.stations.columns) == [
        "md_m",
        "inclination_deg",
        "azimuth_deg",
        "tvd_m",
        "offset_ew_m",
        "offset_ns_m",
        "x_m",
        "y_m",
        "dls_deg_per_30m",
    ]
    assert len(wp.stations) == 3
    assert wp.top_md == 145.90
    assert wp.base_md == 3520.00
    assert wp.stations["tvd_m"].iloc[-1] == 3108.36


def test_alternative_column_spelling(tmp_path: Path) -> None:
    text = SAMPLE.read_text().replace("X_Offset_EW", "X-Offset_EW").replace("X_COORD", "UTM_EW")
    path = tmp_path / "F-11 T2_ACTUAL (NOT ON NPD)"
    path.write_text(text)
    wp = read_wellpath(path)
    assert "offset_ew_m" in wp.stations.columns
    assert "x_m" in wp.stations.columns


def test_unexpected_units_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "F-12_ACTUAL"
    path.write_text(SAMPLE.read_text().replace("m RKB     deg", "ft RKB    deg", 1))
    with pytest.raises(ValueError, match="unexpected units"):
        read_wellpath(path)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("F-12_ACTUAL", False),
        ("F-1 ACTUAL", False),
        ("F-11 T2_ACTUAL (NOT ON NPD)", False),
        ("F-10 A rev#6 PROTOTYPE", True),
        ("F-9A Utsira Water injector Rev10 PLAN", True),
        ("Previous_revision_ACTUAL", False),  # "rev" inside a word is not a revision marker
    ],
)
def test_is_plan(name: str, expected: bool) -> None:
    assert is_plan(Path(name)) is expected
