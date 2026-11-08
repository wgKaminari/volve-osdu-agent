"""Which gold values can a system recover from its inputs at all? (PROJECT_GUIDE.md section 4.4)

A value NPD knows but no input file states (e.g. surface location for wellbores whose LAS has no
LAT/LON) cannot be extracted; the correct output is null, scored as abstention. The search is
deliberately generic (any number within tolerance near the wellbore's name), not the rules
baseline's phrasings, so it doesn't favour one system. Annotations are drafted by code + AI and
marked unreviewed until the owner checks them.
"""

import re
from functools import cache
from pathlib import Path

from volve_osdu.config import Bundle
from volve_osdu.extract.pdf_rules import name_pattern
from volve_osdu.ingest.las import LasLog, read_las
from volve_osdu.ingest.pdf import PdfDocument, normalize_whitespace, read_pdf

TOLERANCE = {
    "kb_elevation_m": 0.2,
    "td_md_m": 0.5,
    "kop_md_m": 0.5,
    "latitude": 1e-4,
    "longitude": 1e-4,
}
LAS_ITEMS = {
    "kb_elevation_m": ["ELEV"],
    "latitude": ["LAT"],
    "longitude": ["LON"],
    "operator": ["COMP"],
    "field": ["FLD"],
    "td_md_m": [],
    "kop_md_m": [],
}
WINDOW_CHARS = 400
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def recoverability(
    bundle: Bundle, wellbore: str, fact: str, gold: str | None, disputed: bool
) -> tuple[bool, str]:
    if fact not in LAS_ITEMS:
        return False, "not scored (constant chosen by the pipeline, e.g. geodatum)"
    if gold is None:
        return False, "NPD has no value (not applicable): correct output is null"
    if disputed:
        return True, "inputs state a value that differs from NPD (disputed)"
    logs = [_las(p) for p in bundle.las if p.is_file()]
    if fact in ("operator", "field"):
        found = [log.path.name for log in logs if _text(log.header_value(LAS_ITEMS[fact][0]))]
        return (
            (True, f"LAS {LAS_ITEMS[fact][0]} in {found[0]}") if found else (False, "not in inputs")
        )

    target, tol = float(gold), TOLERANCE[fact]
    for log in logs:
        for item in LAS_ITEMS[fact]:
            value = log.header_value(item)
            if isinstance(value, float) and abs(value - target) <= tol:
                return True, f"LAS {item} in {log.path.name}"
    if fact in ("td_md_m", "kop_md_m", "kb_elevation_m") and bundle.pdf and bundle.pdf.is_file():
        for page in _pdf(bundle.pdf).pages:
            text = normalize_whitespace(page.text)
            for match in re.finditer(name_pattern(wellbore), text):
                window = text[match.end() : match.end() + WINDOW_CHARS]
                if any(abs(float(n) - target) <= tol for n in NUMBER.findall(window)):
                    return True, f"report p{page.number}, near the wellbore name"
    return False, "no input states this value"


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return None if text.upper() in ("", "UNKNOWN") else text


@cache
def _las(path: Path) -> LasLog:
    return read_las(path)


@cache
def _pdf(path: Path) -> PdfDocument:
    return read_pdf(path)
