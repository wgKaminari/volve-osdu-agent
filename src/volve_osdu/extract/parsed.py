"""Facts read deterministically from LAS headers (method "parsed")."""

from volve_osdu.config import relative
from volve_osdu.extract.names import normalize_wellbore_name
from volve_osdu.facts import Fact, Provenance, ReviewFlag
from volve_osdu.ingest.las import LasLog

FEET_TO_M = 0.3048
# Values the Volve LAS writers use for "not known". Treated as missing, never as data.
PLACEHOLDERS = {"UNKNOWN", "NONE", "N/A", ""}
KB_TYPES = {"KB", "RKB"}


def las_facts(log: LasLog) -> tuple[list[Fact], list[ReviewFlag]]:
    """Header facts from one LAS file, plus info flags for any unit conversion we applied."""
    facts: list[Fact] = []
    flags: list[ReviewFlag] = []

    def prov(mnemonic: str) -> list[Provenance]:
        return [
            Provenance(
                source_file=relative(log.path), locator=f"LAS:~Well/{mnemonic}", method="parsed"
            )
        ]

    for mnemonic in ("WELL", "UWI"):
        raw = _text(log.header_value(mnemonic))
        name = normalize_wellbore_name(raw) if raw else None
        if name:
            # The raw header text is kept as the quote: it becomes a NameAlias ("NO 15/9-F-12").
            source = prov(mnemonic)[0].model_copy(update={"quote": raw})
            facts.append(Fact(name="wellbore_name", value=name, provenance=[source]))

    elev = log.header_value("ELEV")
    elev_type = _text(log.header_value("ELEV_TYPE"))
    if isinstance(elev, float) and elev_type and elev_type.upper() in KB_TYPES:
        unit = log.well["ELEV"].unit.upper()
        if unit in ("M", "METERS", "METRES"):
            facts.append(Fact(name="kb_elevation_m", value=elev, unit="m", provenance=prov("ELEV")))
        elif unit in ("F", "FT", "FEET"):
            fact = Fact(
                name="kb_elevation_m",
                value=round(elev * FEET_TO_M, 4),
                unit="m",
                provenance=prov("ELEV"),
            )
            facts.append(fact)
            flags.append(
                ReviewFlag(
                    severity="info",
                    fact="kb_elevation_m",
                    reason="unit_converted",
                    message=f"{log.path.name}: ELEV {elev} ft converted to metres",
                    candidates=[fact],
                )
            )

    for mnemonic, fact_name in (("LAT", "surface_latitude_deg"), ("LON", "surface_longitude_deg")):
        value = log.header_value(mnemonic)
        if isinstance(value, float):
            facts.append(Fact(name=fact_name, value=value, unit="deg", provenance=prov(mnemonic)))

    for mnemonic, fact_name in (("FLD", "field_name"), ("COMP", "operator_name")):
        value = _text(log.header_value(mnemonic))
        if value:
            facts.append(Fact(name=fact_name, value=value, provenance=prov(mnemonic)))

    return facts, flags


def _text(value: object) -> str | None:
    """Header value as text, or None for blanks and placeholders like "UNKNOWN"."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.upper() in PLACEHOLDERS else text
