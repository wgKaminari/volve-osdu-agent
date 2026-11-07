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
