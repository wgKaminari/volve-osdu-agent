"""Build the held-out ground truth into data/gold/.

Reads NPD wellbore headers (awgeo/Volve_field_data) and Equinor's Well_picks file (spwla_volve)
for the MVP wellbores listed in configs/wells.yaml. Run after scripts/download_data.sh:

    uv run python scripts/build_gold.py
"""

import csv
import logging
from dataclasses import asdict, fields, replace
from pathlib import Path

import yaml

from volve_osdu.config import load_bundles
from volve_osdu.eval.conflicts import CONFLICTS_CSV, write_conflicts
from volve_osdu.eval.gold import (
    GoldValue,
    Pick,
    header_gold,
    parse_well_picks,
    read_npd_development,
    read_npd_exploration,
)
from volve_osdu.eval.recoverable import recoverability

logger = logging.getLogger("build_gold")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
GOLD = ROOT / "data" / "gold"
HEADERS_DIR = RAW / "volve_field_data" / "input_data" / "wellheaders"
NPD_DEVELOPMENT = HEADERS_DIR / "NPD_wellbore_development_all_AW EDIT_FINAL.txt"
NPD_EXPLORATION = HEADERS_DIR / "NPD_wellbore_exploration_all_AW EDIT_FINAL.xls"
WELL_PICKS = RAW / "spwla_volve" / "Well_picks_Volve_v1.dat"


def write_csv(path: Path, rows: list, row_type: type) -> None:
    """Write dataclass instances to CSV, with columns in the dataclass field order."""
    columns = [f.name for f in fields(row_type)]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    logger.info("wrote %d rows to %s", len(rows), path.relative_to(ROOT))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = yaml.safe_load((ROOT / "configs" / "wells.yaml").read_text())
    mvp = [w["canonical_name"] for w in config["wellbores"]]
    GOLD.mkdir(parents=True, exist_ok=True)

    development = header_gold(read_npd_development(NPD_DEVELOPMENT), mvp, "npd_development")
    exploration = header_gold(read_npd_exploration(NPD_EXPLORATION), mvp, "npd_exploration")
    headers = development + exploration
    bundles = {b.canonical_name: b for b in load_bundles()}
    headers = [
        replace(
            g,
            **dict(
                zip(
                    ("recoverable", "recoverable_note"),
                    recoverability(bundles[g.wellbore], g.wellbore, g.fact, g.value, g.disputed),
                    strict=True,
                )
            ),
        )
        for g in headers
    ]
    with_header = {g.wellbore for g in headers}
    for name in mvp:
        if name not in with_header:
            logger.warning("no NPD header for %s: no header gold for this wellbore", name)
    write_csv(GOLD / "wellbore_headers.csv", headers, GoldValue)

    all_picks = parse_well_picks(WELL_PICKS.read_text(encoding="latin-1"))
    picks = [p for p in all_picks if p.wellbore in mvp]
    with_picks = {p.wellbore for p in picks}
    for name in mvp:
        if name not in with_picks:
            logger.warning("no well picks for %s", name)
    write_csv(GOLD / "markers.csv", picks, Pick)
    write_conflicts()
    logger.info("wrote %s", CONFLICTS_CSV.relative_to(ROOT))


if __name__ == "__main__":
    main()
