"""Static curve dictionary: the "rules" baseline for curve mapping (no LLM).

LAS unit spelling -> OSDU UnitOfMeasure code, and mnemonic -> OSDU LogCurveFamily name.
Only unambiguous, widely used mnemonics are listed; everything else stays unmapped (abstain)
and is left for the agent. tests/test_curves.py checks every entry against the pinned lists.
"""

from dataclasses import dataclass

# Keys are upper-cased LAS units. "MD" as a curve unit in Volve files is millidarcy (KLOGH).
UNITS: dict[str, str] = {
    "M": "m",
    "METERS": "m",
    "FT": "ft",
    "API": "gAPI",
    "GAPI": "gAPI",
    "US/FT": "us/ft",
    "US/F": "us/ft",
    "G/CM3": "g/cm3",
    "G/CC": "g/cm3",
    "OHM.M": "ohm.m",
    "OHMM": "ohm.m",
    "V/V": "m3/m3",
    "V/V_DECIMAL": "m3/m3",
    "MD": "mD",
    "IN": "in",
    "INCHES": "in",
    "DEGC": "degC",
    "%": "%",
    "BAR": "bar",
    "M/S": "m/s",
    "M/HR": "m/h",
    "GPA": "GPa",
    "KPA.S/M": "kPa.s/m",
    "PPM": "ppm",
    "UNITLESS": "Euc",
}

FAMILIES: dict[str, str] = {
    "GR": "Gamma Ray",
    "LFP_GR": "Gamma Ray",
    "RHOB": "Bulk Density",
    "LFP_RHOB": "Bulk Density",
    "DEN": "Bulk Density",
    "DRHO": "Bulk Density Correction",
    "NPHI": "Neutron Porosity",
    "LFP_NPHI": "Neutron Porosity",
    "DT": "Compressional Slowness",
    "AC": "Compressional Slowness",
    "LFP_DT": "Compressional Slowness",
    "DTS": "Shear Slowness",
    "LFP_DTS": "Shear Slowness",
    "RD": "Resistivity - Deep",
    "RDEP": "Resistivity - Deep",
    "RM": "Resistivity - Medium",
    "RMED": "Resistivity - Medium",
    "RS": "Resistivity - Shallow",
    "RT": "Resistivity - True Formation",
    "LFP_RT": "Resistivity - True Formation",
    "CALI": "Caliper",
    "LFP_CALI": "Caliper",
    "BS": "Bit Size",
    "LFP_BS": "Bit Size",
    "PEF": "Photoelectric Factor",
    "ROP": "Rate Of Penetration",
    "SW": "Water Saturation",
    "VSH": "Shale Volume Fraction",
    "COAL_FLAG": "Coal Flag",
    "TEMP": "Borehole Temperature",
}


@dataclass(frozen=True)
class CurveMapping:
    mnemonic: str
    unit_code: str | None  # OSDU UnitOfMeasure code, e.g. "gAPI"
    family: str | None  # OSDU LogCurveFamily name, e.g. "Gamma Ray"
    method: str = "rules"


def map_curve(mnemonic: str, las_unit: str) -> CurveMapping:
    return CurveMapping(
        mnemonic=mnemonic,
        unit_code=UNITS.get(las_unit.strip().upper()),
        family=FAMILIES.get(mnemonic.strip().upper()),
    )
