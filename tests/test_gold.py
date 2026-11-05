"""Tests for the ground-truth readers, using tiny fixture files in the real formats."""

from pathlib import Path

from volve_osdu.eval.gold import header_gold, parse_well_picks, read_npd_development

FIXTURES = Path(__file__).parent / "fixtures"
WELL_PICKS_SAMPLE = FIXTURES / "well_picks_sample.dat"
NPD_SAMPLE = FIXTURES / "npd_development_sample.txt"


def test_parse_well_picks_reads_both_blocks() -> None:
    picks = parse_well_picks(WELL_PICKS_SAMPLE.read_text())
    assert [p.wellbore for p in picks] == ["15/5-7 A", "15/9-F-1 B"]


def test_parse_well_picks_values() -> None:
    first, second = parse_well_picks(WELL_PICKS_SAMPLE.read_text())
    assert first.surface == "Sleipner Fm. Top"
    assert first.md_m == 4098.10
    assert first.tvd_m is None
    assert first.qlf is None
    assert second.qlf == "NL"
    assert second.md_m == 886.50
    assert second.tvdss_m == -827.67
    assert second.interpreter == "STAT"


def test_read_npd_development() -> None:
    rows = read_npd_development(NPD_SAMPLE)
    assert len(rows) == 2
    assert rows[0]["Name"] == "15/9-F-1 B"
    assert rows[0]["Geodatum"] == "ED50"  # trailing spaces stripped


def test_header_gold_marks_disputed_and_empty_values() -> None:
    rows = read_npd_development(NPD_SAMPLE)
    gold = header_gold(rows, ["15/9-F-1 B", "15/9-F-12"], "npd_development")
    by_key = {(g.wellbore, g.fact): g for g in gold}

    assert by_key[("15/9-F-1 B", "kop_md_m")].value == "2604.0"
    assert by_key[("15/9-F-1 B", "kop_md_m")].disputed is True
    assert by_key[("15/9-F-12", "kb_elevation_m")].disputed is True
    assert by_key[("15/9-F-12", "kop_md_m")].value is None  # empty in NPD -> None
    assert by_key[("15/9-F-12", "td_md_m")].disputed is False


def test_header_gold_ignores_unwanted_wellbores() -> None:
    gold = header_gold(read_npd_development(NPD_SAMPLE), ["15/9-F-12"], "npd_development")
    assert {g.wellbore for g in gold} == {"15/9-F-12"}
