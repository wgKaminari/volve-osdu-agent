"""Data behind the report figures (HTML report and notebook), computed from results and inputs.

Kept in one place so the two report formats can never disagree.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from volve_osdu.config import ROOT, find_bundle
from volve_osdu.eval.metrics import load_header_gold
from volve_osdu.ingest.las import read_las
from volve_osdu.ingest.wellpath import read_wellpath

RESULTS = ROOT / "docs" / "results.json"
RUN1 = ROOT / "docs" / "results_agent_run1.md"
SYSTEMS = ["rules", "llm_only", "agent"]

# Rows of the run-1 report compared with the current run (label in results.md -> summary key).
RUN1_ROWS = {
    "Field accuracy": "field_accuracy",
    "Abstention accuracy": "abstention_accuracy",
    "Grounding: report facts kept": "grounding_final",
    "Review-flag precision": "flag_precision",
    "Review-flag recall": "flag_recall",
}


def load_results(path: Path = RESULTS) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run1_values(path: Path = RUN1) -> dict[str, float]:
    """Summary values of agent run 1, read from its generated report."""
    text = path.read_text(encoding="utf-8")
    values = {}
    for label, key in RUN1_ROWS.items():
        match = re.search(rf"^\| {re.escape(label)}[^|]*\| (\d+)%", text, re.MULTILINE)
        if match:
            values[key] = int(match.group(1)) / 100
    return values


@dataclass(frozen=True)
class CurveRange:
    mnemonic: str
    file: str  # "input" or "output" LAS
    top_md: float
    base_md: float


def f12_curve_ranges() -> tuple[list[CurveRange], float]:
    """Non-null depth range of every 15/9-F-12 curve, and the MD of the final survey station."""
    bundle = find_bundle("15/9-F-12")
    assert bundle.wellpath is not None
    survey = read_wellpath(bundle.wellpath).base_md
    curves = []
    for path in bundle.las:
        for c in read_las(path).curves:
            if c.top_depth is not None and c.base_depth is not None:
                file = "output" if "OUTPUT" in path.name else "input"
                curves.append(CurveRange(c.mnemonic, file, c.top_depth, c.base_depth))
    return sorted(curves, key=lambda c: -c.base_md), survey


def _to_ecef(lat: float, lon: float, a: float, f: float) -> tuple[float, float, float]:
    e2 = f * (2 - f)
    la, lo = math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return (
        n * math.cos(la) * math.cos(lo),
        n * math.cos(la) * math.sin(lo),
        n * (1 - e2) * math.sin(la),
    )


def _to_geodetic(x: float, y: float, z: float, a: float, f: float) -> tuple[float, float]:
    e2 = f * (2 - f)
    lon, p = math.atan2(y, x), math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * n * math.sin(lat), p)
    return math.degrees(lat), math.degrees(lon)


def ed50_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
    """3-parameter shift (-87, -98, -121 m), EPSG:1133 style; accurate to a few metres here."""
    x, y, z = _to_ecef(lat, lon, 6378388.0, 1 / 297.0)
    return _to_geodetic(x - 87, y - 98, z - 121, 6378137.0, 1 / 298.257223563)


def metres_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate ground distance in metres between two nearby lat/lon points."""
    dlat = (a[0] - b[0]) * 111_320
    dlon = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


@dataclass(frozen=True)
class DatumCheck:
    wellbore: str
    vs_ed50_m: float  # LAS position vs NPD position read as ED50
    vs_wgs84_m: float  # LAS position vs NPD position converted to WGS84


def datum_checks(wellbores: tuple[str, ...] = ("15/9-F-12", "15/9-19 A")) -> list[DatumCheck]:
    """Which datum do the LAS LAT/LON use? Compare with NPD (gold; evaluation code only)."""
    gold = load_header_gold()
    rows = []
    for name in wellbores:
        las = read_las(find_bundle(name).las[0])
        lat, lon = las.header_value("LAT"), las.header_value("LON")
        assert isinstance(lat, float) and isinstance(lon, float)
        npd = (float(gold[(name, "latitude")]["value"]), float(gold[(name, "longitude")]["value"]))
        rows.append(
            DatumCheck(
                name,
                metres_between((lat, lon), npd),
                metres_between((lat, lon), ed50_to_wgs84(*npd)),
            )
        )
    return rows
