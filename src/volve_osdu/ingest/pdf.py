"""PDF text reader: text per page, plus quote lookup used by the grounding check."""

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

# Below this many characters of extractable text per page, a report is mostly images
# (scanned pages, figures, tables as pictures). The F-12 report has ~730 chars/page;
# text-rich Volve reports have 900-1,150. Logged so users know facts may be missed.
IMAGE_HEAVY_CHARS_PER_PAGE = 800


@dataclass(frozen=True)
class PdfPage:
    number: int  # 1-based, as a human would cite it ("p. 5")
    text: str


@dataclass(frozen=True)
class PdfDocument:
    path: Path
    pages: list[PdfPage]

    @property
    def n_chars(self) -> int:
        return sum(len(page.text) for page in self.pages)

    @property
    def is_image_heavy(self) -> bool:
        return self.n_chars / max(len(self.pages), 1) < IMAGE_HEAVY_CHARS_PER_PAGE

    def find_quote(self, quote: str) -> list[int]:
        """Page numbers whose text contains `quote`, ignoring differences in whitespace."""
        needle = normalize_whitespace(quote)
        if not needle:
            return []
        return [p.number for p in self.pages if needle in normalize_whitespace(p.text)]


def normalize_whitespace(text: str) -> str:
    """Collapse spaces, tabs and line breaks to single spaces (PDF line breaks are arbitrary)."""
    return re.sub(r"\s+", " ", text).strip()


def read_pdf(path: Path) -> PdfDocument:
    """Extract the text of every page. Pages without extractable text get an empty string."""
    with pdfplumber.open(path) as pdf:
        pages = [
            PdfPage(number=i, text=page.extract_text() or "")
            for i, page in enumerate(pdf.pages, start=1)
        ]
    return PdfDocument(path=path, pages=pages)