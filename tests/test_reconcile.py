"""Tests for multi-source reconciliation (rule 9)."""

from volve_osdu.facts import Fact, Provenance
from volve_osdu.reconcile import reconcile


def fact(name: str, value: float | str, source: str) -> Fact:
    return Fact(
        name=name,
        value=value,
        provenance=[Provenance(source_file=source, locator="x", method="parsed")],
    )


def test_agreeing_values_merge_sources() -> None:
    resolved, flags = reconcile(
        [fact("kb_elevation_m", 54.9, "a"), fact("kb_elevation_m", 55.0, "b")]
    )
    assert flags == []
    assert resolved["kb_elevation_m"].value == 54.9
    assert len(resolved["kb_elevation_m"].provenance) == 2


def test_conflict_beyond_tolerance_is_flagged_with_all_candidates() -> None:
    resolved, flags = reconcile([fact("kop_md_m", 2617.0, "pdf"), fact("kop_md_m", 2604.0, "las")])
    assert resolved["kop_md_m"].value is None  # tie -> abstain
    assert flags[0].reason == "conflict"
    assert {c.value for c in flags[0].candidates} == {2617.0, 2604.0}


def test_majority_wins_but_is_still_flagged() -> None:
    facts = [
        fact("field_name", "VOLVE", "a"),
        fact("field_name", "volve", "b"),
        fact("field_name", "Q15", "c"),
    ]
    resolved, flags = reconcile(facts)
    assert resolved["field_name"].value == "VOLVE"
    assert len(flags) == 1
