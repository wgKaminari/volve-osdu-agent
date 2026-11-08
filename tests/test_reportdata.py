"""Tests for the data behind the report figures (datum maths, run-1 parsing)."""

from pathlib import Path

from volve_osdu.eval.reportdata import ed50_to_wgs84, metres_between, run1_values


def test_ed50_to_wgs84_shift_matches_the_15_9_19_las_position() -> None:
    # NPD's ED50 position of 15/9-19, converted, lands within a few metres of the LAS LAT/LON.
    wgs84 = ed50_to_wgs84(58.435903, 1.929736)
    assert metres_between(wgs84, (58.435286, 1.928158)) < 5
    assert 100 < metres_between((58.435903, 1.929736), (58.435286, 1.928158)) < 130


def test_run1_values_are_read_from_the_generated_table(tmp_path: Path) -> None:
    report = tmp_path / "run1.md"
    report.write_text(
        "| Metric | agent |\n|---|---|\n"
        "| Field accuracy (recoverable, undisputed) | 91% [78%, 100%] (48/53) |\n"
        "| Review-flag precision | 69% [58%, 88%] (18/26) |\n"
    )
    assert run1_values(report) == {"field_accuracy": 0.91, "flag_precision": 0.69}
