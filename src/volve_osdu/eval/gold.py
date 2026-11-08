"""Readers for the held-out ground truth: NPD wellbore headers and Equinor's Well_picks file.

Only evaluation code may use this module. The agent and the baselines must never read these files.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import xlrd

# Our fact name -> (NPD column name, unit)
NPD_FIELDS: dict[str, tuple[str, str | None]] = {
    "operator": ("Operator", None),
    "field": ("Field", None),
    "kb_elevation_m": ("KBE", "m"),
    "td_md_m": ("Terminal Depth", "m"),
    "kop_md_m": ("Kick off  point [m RKB]", "m"),  # NPD really uses two spaces here
    "latitude": ("Latitude", "deg"),
    "longitude": ("Longitude", "deg"),
    "geodatum": ("Geodatum", None),
}

# Known disagreements between our input files and NPD (PROJECT_GUIDE.md section 4.2).
# These are reported separately in the evaluation. Gold is never "fixed" to match the agent.
DISPUTED: dict[tuple[str, str], str] = {
    ("15/9-F-12", "kb_elevation_m"): "Both F-12 LAS files say 54.9 m KB; NPD says 54.0",
    ("15/9-F-1 B", "kop_md_m"): "F-1 petrophysical report says KOP 2617 m MD RKB; NPD says 2604",
    # Found in M3 by comparing inputs with NPD (docs/architecture.md):
    ("15/9-F-11", "td_md_m"): "NPD's 4562 m is the TD of technical sidetrack F-11 T2; the F-11 "
    "report, well path and LAS all end the original hole at ~347 m",
    ("15/9-F-11 A", "kop_md_m"): "F-11 report says KOP 2586 m MD RKB; NPD says 2578",
    ("15/9-F-11 B", "kop_md_m"): "F-11 report says KOP 2585 m MD RKB; NPD says 2586",
    ("15/9-19 SR", "kb_elevation_m"): "the 15/9-19 SR LAS (LFP) says KB 25.0 m; NPD says 22.0",
    ("15/9-19 A", "latitude"): "LAS LAT/LON are WGS84 (NPD's ED50 position shifted to WGS84 "
    "matches within ~3 m); NPD gives ED50",
    ("15/9-19 A", "longitude"): "LAS LAT/LON are WGS84; NPD gives ED50",
    ("15/9-19 SR", "latitude"): "LAS LAT/LON are WGS84; NPD gives ED50",
    ("15/9-19 SR", "longitude"): "LAS LAT/LON are WGS84; NPD gives ED50",
}

# Names the operator has had over time, as written in our inputs and in NPD. Scoring treats a
# name in the same group as correct ("alias" scoring); "strict" scoring needs an exact match.
OPERATOR_ALIASES: dict[str, set[str]] = {
    "Equinor": {
        "equinor",
        "equinor energy as",
        "statoil",
        "statoil asa",
        "statoil asa (old)",
        "statoil petroleum",
        "statoil petroleum as",
        "statoilhydro",
        "statoilhydro asa",
        "den norske stats oljeselskap a.s",
        "den norske stats oljeselskap as",
    },
}


@dataclass(frozen=True)
class GoldValue:
    wellbore: str
    fact: str
    value: str | None
    unit: str | None
    source: str
    disputed: bool
    note: str
    recoverable: bool | None = None  # can any input file state this value? (recoverable.py)
    recoverable_note: str = ""
    annotations_reviewed: bool = False  # disputed/recoverable notes need the owner's review


@dataclass(frozen=True)
class Pick:
    wellbore: str
    surface: str
    obs: int | None
    qlf: str | None
    md_m: float | None
    tvd_m: float | None
    tvdss_m: float | None
    interpreter: str | None


def read_npd_development(path: Path) -> list[dict[str, str]]:
    """Read the tab-separated NPD development wellbore export (Latin-1 encoded)."""
    with path.open(encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def read_npd_exploration(path: Path) -> list[dict[str, str]]:
    """Read the NPD exploration wellbore export (old Excel .xls format)."""
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    header = [str(cell.value).strip() for cell in sheet.row(0)]
    rows = []
    for i in range(1, sheet.nrows):
        values = [_cell_to_str(cell.value) for cell in sheet.row(i)]
        rows.append(dict(zip(header, values, strict=True)))
    return rows


def _cell_to_str(value: object) -> str:
    """Excel stores all numbers as floats (e.g. 2405.800048828125); round away the float noise."""
    if isinstance(value, float):
        return str(round(value, 6))
    return str(value).strip()


def header_gold(rows: list[dict[str, str]], wellbores: list[str], source: str) -> list[GoldValue]:
    """Turn NPD header rows into one GoldValue per (wellbore, fact), for the wanted wellbores."""
    wanted = set(wellbores)
    gold = []
    for row in rows:
        name = row.get("Name", "")
        if name not in wanted:
            continue
        for fact, (column, unit) in NPD_FIELDS.items():
            raw = row.get(column, "")
            note = DISPUTED.get((name, fact), "")
            gold.append(
                GoldValue(
                    wellbore=name,
                    fact=fact,
                    value=raw or None,
                    unit=unit,
                    source=source,
                    disputed=bool(note),
                    note=note,
                )
            )
    return gold


def parse_well_picks(text: str) -> list[Pick]:
    """Parse Well_picks_Volve_v1.dat.

    The file is fixed-width. Each well block has a header line and a line of dashes; the dashes
    mark where each column starts. Wellbore names look like "NO 15/9-F-1 A"; we drop the "NO ".
    """
    picks: list[Pick] = []
    starts: list[int] = []
    names: list[str] = []
    previous = ""
    for line in text.splitlines():
        if line.strip().startswith("---"):
            starts = [m.start() for m in re.finditer(r"-+", line)]
            names = _slice(previous, starts)
        elif starts and line.startswith("  NO "):
            cells = dict(zip(names, _slice(line, starts), strict=True))
            picks.append(
                Pick(
                    wellbore=cells["Well name"].removeprefix("NO ").strip(),
                    surface=cells["Surface name"],
                    obs=int(cells["Obs#"]) if cells["Obs#"] else None,
                    qlf=cells["Qlf"] or None,
                    md_m=_float(cells["MD"]),
                    tvd_m=_float(cells["TVD"]),
                    tvdss_m=_float(cells["TVDSS"]),
                    interpreter=cells["Intrp"] or None,
                )
            )
        previous = line
    return picks


def _slice(line: str, starts: list[int]) -> list[str]:
    """Cut a fixed-width line into columns. Each column runs until the next one starts."""
    ends = starts[1:] + [len(line)]
    return [line[a:b].strip() for a, b in zip(starts, ends, strict=True)]


def _float(text: str) -> float | None:
    return float(text) if text else None
