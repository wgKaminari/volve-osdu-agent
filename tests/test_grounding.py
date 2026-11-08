"""Tests for rule 8: quotes must be verbatim and contain the value."""

from pathlib import Path

from volve_osdu.facts import Fact, Provenance
from volve_osdu.ingest.pdf import PdfDocument, PdfPage
from volve_osdu.validate.grounding import check_grounding, value_in_quote

DOC = PdfDocument(
    Path("r.pdf"), [PdfPage(5, "15/9-F-1 B was side-tracked from F-1 with KOP @ 2617\nm MD RKB.")]
)


def fact(value: float | str, quote: str, page: int = 5) -> Fact:
    prov = Provenance(
        source_file="r.pdf", locator=f"PDF:p{page}", method="llm_extracted", quote=quote
    )
    return Fact(name="kop_md_m", value=value, provenance=[prov])


def test_verbatim_quote_with_value_passes_even_across_line_breaks() -> None:
    checked, reason = check_grounding(fact(2617.0, "KOP @ 2617 m MD RKB"), DOC)
    assert reason is None and checked is not None


def test_quote_not_in_text_fails() -> None:
    assert check_grounding(fact(2604.0, "KOP @ 2604 m MD RKB"), DOC) == (
        None,
        "quote not found in the report text",
    )


def test_value_must_be_in_the_quote() -> None:
    _, reason = check_grounding(fact(2620.0, "KOP @ 2617 m MD RKB"), DOC)
    assert reason is not None and "not in the quote" in reason


def test_wrong_page_is_corrected_to_where_the_quote_is() -> None:
    checked, _ = check_grounding(fact(2617.0, "KOP @ 2617", page=9), DOC)
    assert checked is not None and checked.provenance[0].locator == "PDF:p5"


def test_value_in_quote_numbers_and_text() -> None:
    assert value_in_quote(3632.0, "TD of 15/9-F-1 was 3632 m")
    assert not value_in_quote(363.0, "TD of 15/9-F-1 was 3632 m")
    assert value_in_quote("F-1", "side-tracked from F-1 with")


def semantic(name: str, value: float | str, quote: str, wellbore: str) -> str | None:
    from volve_osdu.validate.grounding import semantic_problem

    prov = Provenance(source_file="r.pdf", locator="PDF:p4", method="llm_extracted", quote=quote)
    return semantic_problem(Fact(name=name, value=value, provenance=[prov]), wellbore)


def test_semantic_checks_reject_run1_mixups() -> None:
    # The actual run-1 errors (docs/results_agent_run1.md):
    assert semantic("kb_elevation_m", 347.0, "TD of 15/9-F-11 was 347 m MD RKB.", "15/9-F-11")
    assert semantic("kb_elevation_m", 2585.0, "KOP @ 2585 m MD RKB", "15/9-F-11 B")
    assert semantic(
        "kop_md_m",
        257.0,
        "The technical side-track, 15/9-F-11 T2, was kicked off from F-11 @ 257 m MD RKB.",
        "15/9-F-11",
    )
    assert semantic("td_md_m", 3500.0, "3500", "15/9-F-12")
    assert semantic("kickoff_wellbore_name", "15/9-F-12", "Well 15/9-F-12", "15/9-F-12")


def test_semantic_checks_keep_correct_facts() -> None:
    assert (
        semantic(
            "kop_md_m",
            2620.0,
            "15/9-F-1 A was side-tracked from F-1 with KOP @ 2620 m MD RKB.",
            "15/9-F-1 A",
        )
        is None
    )
    assert (
        semantic(
            "kop_md_m",
            257.0,
            "The technical side-track, 15/9-F-11 T2, was kicked off from F-11 @ 257 m MD RKB.",
            "15/9-F-11 T2",
        )
        is None
    )
    assert semantic("td_md_m", 347.0, "TD of 15/9-F-11 was 347 m MD RKB.", "15/9-F-11") is None
    assert semantic("kb_elevation_m", 54.9, "RKB: 54.9 m", "15/9-F-1 A") is None
    assert (
        semantic(
            "kickoff_wellbore_name",
            "15/9-F-1",
            "15/9-F-1 B was side-tracked from F-1",
            "15/9-F-1 B",
        )
        is None
    )
