"""Tests for the PDF reader, using a tiny 2-page text PDF with real F-1 report sentences."""

from pathlib import Path

from volve_osdu.ingest.pdf import PdfDocument, PdfPage, normalize_whitespace, read_pdf

SAMPLE = Path(__file__).parent / "fixtures" / "sample_report.pdf"


def test_read_pdf_pages_are_numbered_from_one() -> None:
    doc = read_pdf(SAMPLE)
    assert [p.number for p in doc.pages] == [1, 2]
    assert "TD of 15/9-F-1 was 3632 m MD RKB" in doc.pages[0].text


def test_find_quote_ignores_line_breaks() -> None:
    doc = read_pdf(SAMPLE)
    # In the PDF, "(Smith" and "Bank Fm.)" are on different lines.
    assert doc.find_quote("TD @ 3682 m MD RKB (Smith Bank Fm.)") == [2]
    assert doc.find_quote("KOP @ 2620 m MD RKB") == [2]


def test_find_quote_returns_nothing_for_invented_text() -> None:
    doc = read_pdf(SAMPLE)
    assert doc.find_quote("KOP @ 2604 m MD RKB") == []
    assert doc.find_quote("   ") == []


def test_image_heavy_detection() -> None:
    sparse = PdfDocument(path=Path("x.pdf"), pages=[PdfPage(1, "a" * 100), PdfPage(2, "")])
    rich = PdfDocument(path=Path("y.pdf"), pages=[PdfPage(1, "a" * 1200)])
    assert sparse.is_image_heavy
    assert not rich.is_image_heavy


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  TD @\n3682   m\tMD ") == "TD @ 3682 m MD"
