"""Well path (deviation survey) reader for the Volve *_ACTUAL / PLAN text tables."""

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# A file whose name matches this is a plan or prototype, never the drilled ("actual") trajectory.
# Examples: "F-10 A rev#6 PROTOTYPE", "F-9A Utsira Water injector Rev10 PLAN".
PLAN_PATTERN = re.compile(r"\b(PLAN|PROTOTYPE)\b|\brev\s*#?\d+", re.IGNORECASE)

# Source column name -> our column name. The files use two spellings for the same columns.
COLUMNS = {
    "MD": "md_m",
    "Inc": "inclination_deg",
    "Azim": "azimuth_deg",
    "TVD": "tvd_m",
    "X_Offset_EW": "offset_ew_m",
    "X-Offset_EW": "offset_ew_m",
    "Y_Offset_NS": "offset_ns_m",
    "Y-Offset_NS": "offset_ns_m",
    "X_COORD": "x_m",
    "UTM_EW": "x_m",
    "Y_COORD": "y_m",
    "UTM_NS": "y_m",
    "DLS": "dls_deg_per_30m",
}

# The unit line every Volve well path file has. Anything else is rejected rather than guessed.
EXPECTED_UNITS = "m RKB deg deg m RKB m m m m deg/30m"


@dataclass(frozen=True)
class WellPath:
    """A parsed well path. MD and TVD are metres below the rotary kelly bushing (RKB)."""

    path: Path
    is_plan: bool
    stations: pd.DataFrame

    @property
    def top_md(self) -> float:
        return float(self.stations["md_m"].iloc[0])

    @property
    def base_md(self) -> float:
        """MD of the last survey station: the deepest point the actual trajectory describes."""
        return float(self.stations["md_m"].iloc[-1])


def is_plan(path: Path) -> bool:
    """True if the file name marks a plan or prototype rather than the drilled well path."""
    return bool(PLAN_PATTERN.search(path.name))


def read_wellpath(path: Path) -> WellPath:
    """Read a whitespace-separated well path table: a name line, a unit line, then stations."""
    lines = [line for line in path.read_text(encoding="latin-1").splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError(f"{path.name}: expected a name line, a unit line and stations")

    names = lines[0].split()
    unknown = [n for n in names if n not in COLUMNS]
    if unknown:
        raise ValueError(f"{path.name}: unknown columns {unknown}")

    units = " ".join(lines[1].split())
    if units != EXPECTED_UNITS:
        raise ValueError(f"{path.name}: unexpected units {units!r}")

    rows = []
    for number, line in enumerate(lines[2:], start=3):
        values = line.split()
        if len(values) != len(names):
            raise ValueError(
                f"{path.name} line {number}: {len(values)} values, expected {len(names)}"
            )
        rows.append([float(v) for v in values])

    stations = pd.DataFrame(rows, columns=[COLUMNS[n] for n in names])
    return WellPath(path=path, is_plan=is_plan(path), stations=stations)
