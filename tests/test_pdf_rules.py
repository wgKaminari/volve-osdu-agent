"""Tests for the regex PDF extractor (rules baseline), on text copied from the Volve reports."""

from pathlib import Path

from volve_osdu.extract.pdf_rules import pdf_rule_facts
from volve_osdu.ingest.pdf import PdfDocument, PdfPage

F1_REPORT = PdfDocument(
    path=Path("report.pdf"),
    pages=[
        PdfPage(4, "2.1 Summary 15/9-F-1\nTD of 15/9-F-1 was 3632 m MD RKB (Smith Bank Fm.)."),
        PdfPage(
            5,
            "15/9-F-1 A was side-tracked from F-1 with KOP @ 2620 m MD RKB. TD @ 3682 m MD\nRKB "
            "(Smith Bank Fm.). 15/9-F-1 B was side-tracked from F-1 with KOP @ 2617 m MD RKB. "
            "TD @ 3465 m MD RKB (Sleipner Fm.).",
        ),
        PdfPage(25, "Well: 15/9-F-1 A Date: 26. August 2013 Rig: Mærsk Inspirer RKB: 54.9 m"),
    ],
)


def values(name: str) -> dict[str, float | str | None]:
    return {f.name: f.value for f in pdf_rule_facts(F1_REPORT, name)}


def test_shared_report_facts_go_to_the_right_wellbore() -> None:
    assert values("15/9-F-1") == {"td_md_m": 3632.0}
    assert values("15/9-F-1 A") == {
        "kickoff_wellbore_name": "15/9-F-1",
        "kop_md_m": 2620.0,
        "td_md_m": 3682.0,
        "kb_elevation_m": 54.9,
    }
    assert values("15/9-F-1 B")["kop_md_m"] == 2617.0


def test_facts_carry_page_and_verbatim_quote() -> None:
    facts = pdf_rule_facts(F1_REPORT, "15/9-F-1 B")
    prov = facts[0].provenance[0]
    assert prov.locator == "PDF:p5"
    assert prov.quote is not None and "KOP @ 2617 m MD RKB" in prov.quote
    assert F1_REPORT.find_quote(prov.quote) == [5]


def test_unknown_wellbore_gives_nothing() -> None:
    assert values("15/9-F-1 C") == {}
