"""Wellbore name normalization (NPD style: "15/9-F-1 A", "15/9-19 BT2")."""

import re

from volve_osdu.facts import Fact

# Block/well, optional platform ("F-"), well number, optional sidetrack suffix (A, BT2, SR).
_NAME = re.compile(r"^(\d+/\d+-(?:[A-Z]-)?\d+)\s*([A-Z]{1,2}\d?)?$")
_PREFIX = re.compile(r"^NO[\s_]+")


def normalize_wellbore_name(raw: str) -> str | None:
    """ "NO_15/9-19_A" -> "15/9-19 A", "NO 15/9-F-12" -> "15/9-F-12". None if not a well name."""
    text = _PREFIX.sub("", raw.strip().upper())
    text = re.sub(r"[\s_]+", " ", text).strip()
    match = _NAME.match(text)
    if not match:
        return None
    base, suffix = match.groups()
    return f"{base} {suffix}" if suffix else base


def well_name_of(wellbore_name: str) -> str:
    """The well a wellbore belongs to; sidetracks share it: "15/9-F-1 A" -> "15/9-F-1"."""
    match = _NAME.match(wellbore_name)
    return match.group(1) if match else wellbore_name


def short_to_full(name: str, block: str = "15/9") -> str | None:
    """Report prose often drops the block: "F-11 T2" -> "15/9-F-11 T2"."""
    if not re.match(r"^\d+/\d+-", name):
        name = f"{block}-{name}"
    return normalize_wellbore_name(name)


def most_specific_name(names: list[Fact]) -> Fact | None:
    """The longest parsed wellbore name ("15/9-19 A" over "15/9-19"), with all its sources."""
    if not names:
        return None
    best = max(names, key=lambda f: len(str(f.value)))
    sources = [p for f in names if f.value == best.value for p in f.provenance]
    return Fact(name="wellbore_name", value=best.value, provenance=sources)
