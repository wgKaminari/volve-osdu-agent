"""Tools the agent's nodes use: reference-value lookup and PDF page retrieval."""

import difflib
import re
from functools import cache
from urllib.parse import unquote

from volve_osdu.config import REFERENCE_DIR
from volve_osdu.ingest.pdf import PdfDocument, PdfPage, normalize_whitespace
from volve_osdu.osdu.reference import load_reference_ids

LOOKUP_FILES = {"UnitOfMeasure": "UnitOfMeasure.1.json", "LogCurveFamily": "LogCurveFamily.1.json"}


@cache
def reference_codes(kind: str) -> tuple[str, ...]:
    """Decoded codes of one pinned reference list: "Gamma Ray", "gAPI", ..."""
    ids = load_reference_ids(REFERENCE_DIR / LOOKUP_FILES[kind], "ns")
    prefix = f"ns:reference-data--{kind}:"
    return tuple(sorted(unquote(i.removeprefix(prefix).removesuffix(":")) for i in ids))


def exists(kind: str, code: str) -> bool:
    return code in set(reference_codes(kind))


def lookup_reference(kind: str, query: str, top_k: int = 5) -> list[str]:
    """Closest codes to `query` by spelling and shared words; used to repair near-misses."""
    q = query.lower()
    q_words = set(re.findall(r"[a-z0-9]+", q))

    def score(code: str) -> float:
        c = code.lower()
        words = set(re.findall(r"[a-z0-9]+", c))
        overlap = len(q_words & words) / max(len(q_words | words), 1)
        return difflib.SequenceMatcher(None, q, c).ratio() + overlap

    return sorted(reference_codes(kind), key=score, reverse=True)[:top_k]


KEYWORDS = ("TD", "KOP", "RKB", "side-track", "kicked off", "kick off", "total depth")


def search_pdf(
    doc: PdfDocument, wellbore: str, max_pages: int = 6, max_chars: int = 16000
) -> list[PdfPage]:
    """Pages most likely to state this wellbore's depths: the name plus depth keywords."""
    scored = []
    for page in doc.pages:
        text = normalize_whitespace(page.text)
        name_hits = text.count(wellbore)
        keyword_hits = sum(text.count(k) for k in KEYWORDS)
        if name_hits:
            scored.append((name_hits * 3 + min(keyword_hits, 10), page))
    scored.sort(key=lambda item: (-item[0], item[1].number))
    chosen, total = [], 0
    for _score, page in scored[:max_pages]:
        if total + len(page.text) > max_chars and chosen:
            break
        chosen.append(page)
        total += len(page.text)
    return sorted(chosen, key=lambda p: p.number)
