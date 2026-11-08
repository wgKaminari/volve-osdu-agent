"""Draft data/gold/curve_labels.csv: OSDU unit code + LogCurveFamily for every Volve LAS curve.

AI-drafted gold (Claude, 2026-11-08). Every row starts as reviewed=false; only the owner sets
reviewed=true. The script refuses to overwrite a file that already has reviewed rows.

    uv run python scripts/draft_curve_labels.py
"""

import csv
import logging
import sys
from collections import Counter

from volve_osdu.config import ROOT, load_bundles
from volve_osdu.ingest.las import read_las

OUT = ROOT / "data" / "gold" / "curve_labels.csv"

UNIT = {
    "g/cm3": "g/cm3",
    "G/CC": "g/cm3",
    "G/CM3": "g/cm3",
    "API": "gAPI",
    "GAPI": "gAPI",
    "US/F": "us/ft",
    "us/ft": "us/ft",
    "IN": "in",
    "inches": "in",
    "V/V": "m3/m3",
    "v/v": "m3/m3",
    "v/v_decimal": "m3/m3",
    "unitless": "Euc",
    "UNITLESS": "Euc",
    "MD": "mD",
    "mD": "mD",
    "ohm.m": "ohm.m",
    "OHMM": "ohm.m",
    "m/hr": "m/h",
    "DEGC": "degC",
    "degC": "degC",
    "%": "%",
    "bar": "bar",
    "m/s": "m/s",
    "GPa": "GPa",
    "kPa.s/m": "kPa.s/m",
    "ppm": "ppm",
    "meters": "m",
}
UNIT_NOTE = {
    "UNKNOWN": "unit stated as UNKNOWN: abstain",
    "": "no unit given: abstain",
    "b/elec": "barns/electron has no code in the pinned UnitOfMeasure list",
    "scm(15C)/scmUNKNOWN": "garbled unit string: abstain",
}
H, M = "high", "medium"
F = {  # mnemonic -> (family, confidence, note)
    "AC": ("Compressional Slowness", H, "description: Sonic Transit Time (Slowness)"),
    "BS": ("Bit Size", H, ""),
    "LFP_BS": ("Bit Size", H, ""),
    "CALI": ("Caliper", H, ""),
    "LFP_CALI": ("Caliper", H, ""),
    "COAL_FLAG": ("Coal Flag", H, ""),
    "LFP_COAL": ("Coal Flag", M, "LFP coal indicator"),
    "DEN": ("Bulk Density", H, "description: Bulk Density"),
    "DRHO": ("Bulk Density Correction", H, ""),
    "DT": ("Compressional Slowness", H, ""),
    "LFP_DT": ("Compressional Slowness", H, ""),
    "LFP_DT_LOG": ("Compressional Slowness", H, "measured log"),
    "DTS": ("Shear Slowness", H, ""),
    "LFP_DTS": ("Shear Slowness", H, ""),
    "LFP_DTS_LOG": ("Shear Slowness", H, ""),
    "GR": ("Gamma Ray", H, ""),
    "LFP_GR": ("Gamma Ray", H, ""),
    "NBGRCFM": ("Gamma Ray", H, "near-bit GR (Baker)"),
    "GRMAX": ("Gamma Ray Shale", H, "description: Gamma Ray Shale Value"),
    "LFP_GRMAX": ("Gamma Ray Shale", M, ""),
    "GRMIN": ("Gamma Ray Clean", H, "description: Gamma Ray Clean Value"),
    "LFP_GRMIN": ("Gamma Ray Clean", M, ""),
    "KLOGH": ("Horizontal Permeability", H, "description: Calculated Horizontal PERMEABILITY"),
    "KLOGV": ("Vertical Permeability", H, "description: Vertical PERMEABILITY"),
    "LFP_AI": ("Acoustic Impedance", H, ""),
    "LFP_AI_LOG": ("Acoustic Impedance", H, ""),
    "LFP_GAS": ("Gas Flag", M, "LFP fluid flag"),
    "LFP_GOR": ("Gas Oil Ratio", M, ""),
    "LFP_NPHI": ("Neutron Porosity", H, ""),
    "NPHI": ("Neutron Porosity", H, ""),
    "NEU": ("Neutron Porosity", H, ""),
    "LFP_PHIE": ("Effective Porosity", H, ""),
    "LFP_PHIT": ("Total Porosity", H, ""),
    "LFP_PRESS": ("Formation Pressure", M, ""),
    "LFP_RHOB": ("Bulk Density", H, ""),
    "LFP_RHOB_LOG": ("Bulk Density", H, ""),
    "RHOB": ("Bulk Density", H, ""),
    "LFP_RHOG": ("Grain Density", H, ""),
    "LFP_RHOHA": ("Hydrocarbon Density", M, "apparent HC density"),
    "LFP_RHOMF": ("Mud Filtrate Density", H, ""),
    "RHOFL": ("Fluid Density", M, "description gives constant 0.9"),
    "LFP_RT": ("Resistivity - True Formation", H, ""),
    "RT": ("Resistivity - True Formation", H, ""),
    "LFP_RW": ("Water Resistivity", H, ""),
    "RW": ("Water Resistivity", M, "RW = formation water resistivity"),
    "LFP_RXO": ("Resistivity - Flushed Zone", H, ""),
    "LFP_SAL": ("Formation Water Salinity", M, ""),
    "LFP_SI": ("Acoustic Impedance Shear", M, ""),
    "LFP_SI_LOG": ("Acoustic Impedance Shear", M, ""),
    "LFP_SGT": ("Gas Saturation", M, "total gas saturation"),
    "LFP_SOT": ("Oil Saturation", M, "total oil saturation"),
    "LFP_SWE": ("Effective Water Saturation", H, ""),
    "LFP_SWT": ("Water Saturation", M, "total water saturation"),
    "LFP_SXOWE": ("Flushed Zone Water Saturation", M, ""),
    "LFP_SXOWT": ("Flushed Zone Water Saturation", M, ""),
    "LFP_SXOGT": ("Flushed Zone Gas Saturation", M, ""),
    "LFP_SXOOT": ("Flushed Zone Oil Saturation", M, ""),
    "LFP_TEMP": ("Formation Temperature", M, ""),
    "TEMP": ("Formation Temperature", M, "description: Calculated temperature curve"),
    "LFP_TVD": ("True Vertical Depth", H, ""),
    "LFP_TVDSS": ("True Vertical Depth Sub Sea", H, ""),
    "LFP_TVDML": ("True Vertical Depth Below Mudline", H, ""),
    "LFP_VCARB": ("Carbonate Volume Fraction", H, ""),
    "VCARB": ("Carbonate Volume Fraction", H, ""),
    "LFP_VP": ("Compressional Velocity", H, ""),
    "LFP_VP_LOG": ("Compressional Velocity", H, ""),
    "LFP_VS": ("Shear Velocity", H, ""),
    "LFP_VS_LOG": ("Shear Velocity", H, ""),
    "LFP_VQRTZ": ("Quartz Volume Fraction", M, ""),
    "LFP_VSH": ("Shale Volume Fraction", H, ""),
    "VSH": ("Shale Volume Fraction", H, ""),
    "LFP_VSHDN": ("Shale Volume Fraction", M, "density-neutron VSH"),
    "LFP_VSHGR": ("Shale Volume Fraction", M, "GR VSH"),
    "LFP_VSHDRY": ("Shale Volume Fraction", M, "dry shale volume"),
    "N": ("Archie Saturation Exponent n", M, "description: Saturation exponent"),
    "PEF": ("Photoelectric Factor", H, ""),
    "PHIF": ("Effective Porosity", M, "Equinor CPI final porosity"),
    "PORD": ("Density Porosity", H, "description: Density porosity"),
    "RACEHM": ("Resistivity - Attenuation", M, "Baker attenuation resistivity"),
    "RACELM": ("Resistivity - Attenuation", M, ""),
    "RPCEHM": ("Resistivity - Phase Shift", M, "Baker phase resistivity"),
    "RPCELM": ("Resistivity - Phase Shift", M, ""),
    "RD": ("Resistivity - Deep", H, ""),
    "RDEP": ("Resistivity - Deep", H, "description: Deep Resistivity"),
    "RM": ("Resistivity - Medium", H, ""),
    "RMED": ("Resistivity - Medium", H, "description: Medium Resistivity"),
    "RS": ("Resistivity - Shallow", H, ""),
    "ROP": ("Rate Of Penetration", H, ""),
    "ROP5_RM": ("Rate Of Penetration", M, "ROP averaged (5 ft running mean)"),
    "SW": ("Water Saturation", H, ""),
    "SWIRR": ("Irreducible Water Saturation", M, "formula from KLOGH"),
}
# Fluid-substituted (_B brine, _G gas, _O oil, _V virgin), clipped (C, WC) and synthetic variants
# keep the family of their base curve, with medium confidence.
VARIANT_BASE = {
    "LFP_AI_": "LFP_AI",
    "LFP_DT_": "LFP_DT",
    "LFP_DTS_": "LFP_DTS",
    "LFP_EI_HILT_": None,
    "LFP_PR": None,
    "LFP_RHOB_": "LFP_RHOB",
    "LFP_VP_": "LFP_VP",
    "LFP_VS_": "LFP_VS",
    "LFP_PHIE": "LFP_PHIE",
    "LFP_PHIT": "LFP_PHIT",
    "LFP_SWE": "LFP_SWE",
    "LFP_SWT": "LFP_SWT",
    "LFP_VCARB": "LFP_VCARB",
    "LFP_VQRTZ": "LFP_VQRTZ",
    "LFP_VSHDRY": "LFP_VSHDRY",
    "LFP_SXOWE": "LFP_SXOWE",
    "LFP_SXOWT": "LFP_SXOWT",
    "LFP_RHOFL": None,
}
NULL_NOTE = {
    "BADDATA_FLAG": "bad-data flag: no matching family",
    "LFP_BADDATA": "bad-data flag",
    "BVW": "bulk volume water: no matching family in the pinned list",
    "BWV": "unclear",
    "CARB_FLAG": "carbonate flag: no matching family",
    "DELTA": "NPHI-PORD difference",
    "J": "Leverett J computed curve",
    "KLHC_INT": "unclear",
    "M": "cementation exponent formula",
    "PERF_FLAG": "perforation flag",
    "RHOMA": "constant matrix density",
    "SAND_FLAG": "no Sand Flag family",
}


def family(m):
    if m in F:
        return F[m]
    if m.startswith("LFP_EI_HILT_"):
        return ("Elastic Impedance", M, "fluid-substituted elastic impedance")
    if m.startswith("LFP_PR") and not m.startswith("LFP_PRESS"):
        return ("Poisson Ratio (Dynamic)", M, "dynamic Poisson ratio variant")
    if m.startswith("LFP_RHOFL"):
        return ("Fluid Density", M, "pore fluid density variant")
    for prefix, base in VARIANT_BASE.items():
        if base and m.startswith(prefix) and m != base:
            return (F[base][0], M, f"variant of {base}")
    return (
        None,
        "",
        NULL_NOTE.get(m, "meaning not clear enough from mnemonic/description: abstain"),
    )


def main() -> None:
    if OUT.exists() and any(r["reviewed"] == "true" for r in csv.DictReader(OUT.open())):
        sys.exit(f"{OUT} has reviewed rows; edit it by hand instead of re-drafting")
    pairs: Counter[tuple[str, str]] = Counter()
    for b in load_bundles():
        for p in b.las:
            for c in read_las(p).curves:
                pairs[(c.mnemonic, c.unit)] += 1
    rows = []
    for (m, u), n in sorted(pairs.items()):
        fam, conf, note = family(m)
        unit = UNIT.get(u)
        unote = UNIT_NOTE.get(u, "") if unit is None else ""
        rows.append(
            {
                "mnemonic": m,
                "las_unit": u,
                "uom_code": unit or "",
                "family": fam or "",
                "confidence": conf,
                "occurrences": n,
                "note": "; ".join(x for x in (note, unote) if x),
                "drafted_by": "claude",
                "reviewed": "false",
            }
        )
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.info(
        "drafted %d curve labels into %s (reviewed=false)", len(rows), OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    main()
