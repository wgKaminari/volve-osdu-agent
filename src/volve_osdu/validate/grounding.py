"""Rule 8: an llm_extracted fact must quote its source verbatim, and the value must be in the quote.

Whitespace is normalized (PDF line breaks are arbitrary); nothing else is forgiven. A fact that
fails is dropped by the caller and reported as an "ungrounded" warn flag.
"""

import re

from volve_osdu.facts import Fact
from volve_osdu.ingest.pdf import PdfDocument, normalize_whitespace

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def value_in_quote(value: float | str | None, quote: str) -> bool:
    if value is None:
        return False
    if isinstance(value, float | int):
        numbers = [float(n.replace(",", ".")) for n in NUMBER.findall(quote)]
        return any(abs(n - float(value)) < 1e-6 for n in numbers)
    return normalize_whitespace(str(value)).casefold() in normalize_whitespace(quote).casefold()


def check_grounding(fact: Fact, doc: PdfDocument) -> tuple[Fact | None, str | None]:
    """Return (fact with the verified page as locator, None) or (None, reason it failed)."""
    prov = fact.provenance[0] if fact.provenance else None
    if prov is None or not prov.quote:
        return None, "no quote"
    pages = doc.find_quote(prov.quote)
    if not pages:
        return None, "quote not found in the report text"
    if not value_in_quote(fact.value, prov.quote):
        return None, f"value {fact.value!r} is not in the quote"
    cited = int(prov.locator.removeprefix("PDF:p")) if prov.locator.startswith("PDF:p") else None
    page = cited if cited in pages else pages[0]
    fixed = prov.model_copy(update={"locator": f"PDF:p{page}"})
    return fact.model_copy(update={"provenance": [fixed]}), None
