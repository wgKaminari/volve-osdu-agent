"""Command-line entry point: `volve-osdu run --wellbore "15/9-F-12" --system rules`."""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from volve_osdu.config import ROOT, find_bundle, load_bundles, namespace
from volve_osdu.pipeline import SYSTEMS, run_wellbore

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="volve-osdu", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="convert wellbore bundles into OSDU manifests")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument("--wellbore", help='canonical name or folder, e.g. "15/9-F-12"')
    target.add_argument("--all", action="store_true", help="every MVP wellbore in wells.yaml")
    run.add_argument("--system", default="rules", choices=sorted(SYSTEMS))
    run.add_argument("--out", type=Path, default=ROOT / "outputs")
    run.add_argument("--run-id", help="output folder name (default: UTC timestamp + system)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("lasio").setLevel(logging.ERROR)  # noisy about wrapped-line LAS files

    run_id = args.run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{args.system}"
    bundles = load_bundles() if args.all else [find_bundle(args.wellbore)]
    results = [run_wellbore(b, args.system, args.out / run_id, namespace()) for b in bundles]
    invalid = [r.wellbore for r in results if not r.valid]
    logger.info(
        "run %s: %d wellbore(s), %d not valid %s", run_id, len(results), len(invalid), invalid or ""
    )
    return 1 if invalid else 0
