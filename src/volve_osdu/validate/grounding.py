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


# --- Semantic checks (added after agent run 1, see docs/results_agent_run1.md) ----------------
# A verbatim quote proves a number is in the report, not that it is the right fact for the right
# wellbore: run 1 took "TD of 15/9-F-11 was 347 m" as the KB elevation and the kick-off point of
# 15/9-F-11 T2 as that of 15/9-F-11. These generic checks reject such pairings.

FACT_KEYWORDS = {
    "td_md_m": re.compile(r"\bTD\b|total depth", re.IGNORECASE),
    "kop_md_m": re.compile(r"\bKOP\b|kick(?:ed)?[- ]?off", re.IGNORECASE),
    "kb_elevation_m": re.compile(r"\bR?KB\b|elevation|kelly", re.IGNORECASE),
    "kickoff_wellbore_name": re.compile(r"side-?track|kick(?:ed)?[- ]?off", re.IGNORECASE),
}
FACT_LABELS = {
    "td_md_m": "total depth",
    "kop_md_m": "kick-off point",
    "kb_elevation_m": "KB elevation",
    "kickoff_wellbore_name": "parent wellbore",
}
# Physically plausible ranges for Volve (metres). Outside them a value is a mix-up, not a fact.
FACT_RANGES = {
    "td_md_m": (50.0, 10000.0),
    "kop_md_m": (1.0, 10000.0),
    "kb_elevation_m": (0.0, 150.0),
}
WELLBORE_NAME = re.compile(r"\b\d+/\s?\d+-(?:[A-Z]-)?\d+(?:\s?(?:[A-D]|T\d|BT\d|SR)\b)?")


def semantic_problem(fact: Fact, wellbore: str) -> str | None:
    """Why `fact` cannot be this wellbore's value, or None if it passes."""
    prov = fact.provenance[0] if fact.provenance else None
    quote = normalize_whitespace(prov.quote or "") if prov else ""
    keyword = FACT_KEYWORDS.get(fact.name)
    if keyword and not keyword.search(quote):
        return f"quote does not state a {FACT_LABELS.get(fact.name, fact.name)}"
    if fact.name in FACT_RANGES and isinstance(fact.value, float | int):
        low, high = FACT_RANGES[fact.name]
        if not low <= float(fact.value) <= high:
            return f"{fact.value} m is not a plausible {fact.name} (expected {low}-{high} m)"
    named = {
        re.sub(r"\s+", " ", n.replace("/ ", "/")).strip() for n in WELLBORE_NAME.findall(quote)
    }
    if named and wellbore not in named:
        return f"quote is about {', '.join(sorted(named))}, not {wellbore}"
    if fact.name == "kickoff_wellbore_name" and str(fact.value) == wellbore:
        return "a wellbore cannot be kicked off from itself"
    return None
