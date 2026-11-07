"""Tests for header facts read from LAS files."""

from pathlib import Path

from volve_osdu.extract.parsed import las_facts
from volve_osdu.ingest.las import read_las

SAMPLE = Path(__file__).parent / "fixtures" / "sample.las"


def test_las_facts_from_header() -> None:
    facts, flags = las_facts(read_las(SAMPLE))
    values = {(f.name, f.value) for f in facts}
    assert ("wellbore_name", "15/9-F-12") in values
    assert ("kb_elevation_m", 54.9) in values
    assert ("surface_latitude_deg", 58.441713) in values
    assert ("field_name", "VOLVE") in values
    assert ("operator_name", "STATOILHYDRO") in values
    assert flags == []


def test_every_fact_has_parsed_provenance_with_locator() -> None:
    facts, _ = las_facts(read_las(SAMPLE))
    for fact in facts:
        assert fact.provenance[0].method == "parsed"
        assert fact.provenance[0].locator.startswith("LAS:~Well/")


def test_uwi_raw_text_is_kept_as_quote_for_aliases() -> None:
    facts, _ = las_facts(read_las(SAMPLE))
    quotes = {f.provenance[0].quote for f in facts if f.name == "wellbore_name"}
    assert quotes == {"15/9-F-12", "NO 15/9-F-12"}
