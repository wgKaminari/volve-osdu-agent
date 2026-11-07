"""Rule-based (regex) facts from petrophysical report text: the "rules" baseline, no LLM.

The Volve reports state key depths in a few fixed phrasings, for example:
  "TD of 15/9-F-1 was 3632 m MD RKB"
  "15/9-F-1 A was side-tracked from F-1 with KOP @ 2620 m MD RKB. TD @ 3682 m MD RKB"
  "The technical side-track, 15/9-F-11 T2, was kicked off from F-11 @ 257 m MD RKB. TD @ 4562"
  "Well: 15/9-F-1 A Date: 26. August 2013 Rig: Mærsk Inspirer RKB: 54.9 m"
One report often covers several wellbores, so every pattern is anchored on the exact name.
"""

import re

from volve_osdu.config import relative
from volve_osdu.extract.names import short_to_full
from volve_osdu.facts import Fact, Provenance
from volve_osdu.ingest.pdf import PdfDocument, normalize_whitespace

NUM = r"(\d{2,5}(?:\.\d+)?)"
PARENT = r"((?:\d+/\d+-)?F-\d+(?: ?[A-Z]\d?)?)"


def name_pattern(wellbore_name: str) -> str:
    """Regex for the exact name: "15/9-F-1" must not match inside "15/9-F-1 A" or "15/9-F-11"."""
    return re.escape(wellbore_name) + r"(?!\d)(?!\s?(?:[A-D]|T\d|BT\d|SR)\b)"


def pdf_rule_facts(doc: PdfDocument, wellbore_name: str) -> list[Fact]:
    name = name_pattern(wellbore_name)
    patterns: list[tuple[str, list[str]]] = [
        (rf"TD of {name} was {NUM} ?m MD RKB", ["td_md_m"]),
        (
            rf"{name} was side-tracked from {PARENT} with KOP @ {NUM} ?m MD RKB\.? "
            rf"TD @ {NUM} ?m MD RKB",
            ["kickoff_wellbore_name", "kop_md_m", "td_md_m"],
        ),
        (
            rf"side-track, {name}, was kicked off from {PARENT} @ {NUM} ?m MD RKB\.? "
            rf"TD @ {NUM} ?m MD RKB",
            ["kickoff_wellbore_name", "kop_md_m", "td_md_m"],
        ),
        (rf"Well: {name} Date: .{{0,60}}? RKB: {NUM} ?m", ["kb_elevation_m"]),
    ]
    facts: list[Fact] = []
    for page in doc.pages:
        text = normalize_whitespace(page.text)
        for pattern, names in patterns:
            for match in re.finditer(pattern, text):
                quote = match.group(0)
                for fact_name, raw in zip(names, match.groups(), strict=True):
                    value: float | str | None
                    if fact_name == "kickoff_wellbore_name":
                        value = short_to_full(raw)
                        unit = None
                    else:
                        value, unit = float(raw), "m"
                    if value is None:
                        continue
                    facts.append(
                        Fact(
                            name=fact_name,
                            value=value,
                            unit=unit,
                            provenance=[
                                Provenance(
                                    source_file=relative(doc.path),
                                    locator=f"PDF:p{page.number}",
                                    method="parsed",
                                    quote=quote,
                                )
                            ],
                        )
                    )
    return facts
