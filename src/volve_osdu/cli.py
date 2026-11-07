"""Command-line entry point: `volve-osdu run --wellbore "15/9-F-12" --system rules`."""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from volve_osdu.config import ROOT, find_bundle, load_bundles, namespace
from volve_osdu.pipeline import SYSTEMS, System, run_wellbore

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="volve-osdu", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="convert wellbore bundles into OSDU manifests")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument("--wellbore", help='canonical name or folder, e.g. "15/9-F-12"')
    target.add_argument("--all", action="store_true", help="every MVP wellbore in wells.yaml")
    run.add_argument("--system", default="rules", choices=sorted([*SYSTEMS, "agent"]))
    run.add_argument("--out", type=Path, default=ROOT / "outputs")
    run.add_argument("--run-id", help="output folder name (default: UTC timestamp + system)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("lasio").setLevel(logging.ERROR)  # noisy about wrapped-line LAS files

    run_id = args.run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{args.system}"
    bundles = load_bundles() if args.all else [find_bundle(args.wellbore)]
    system: str | System = args.system
    llm = None
    if args.system == "agent":
        from volve_osdu.agent.llm import from_env
        from volve_osdu.agent.system import AgentSystem

        try:
            llm = from_env()
        except RuntimeError as exc:
            logger.error("%s", exc)
            return 2
        system = AgentSystem(llm)
    results = [run_wellbore(b, system, args.out / run_id, namespace()) for b in bundles]
    if llm is not None:
        cached = sum(t["cached"] for t in llm.trace)
        tokens = sum(t["prompt_tokens"] + t["completion_tokens"] for t in llm.trace)
        logger.info(
            "LLM: %d calls (%d API, %d from cache), %d tokens, model %s",
            len(llm.trace),
            llm.api_calls,
            cached,
            tokens,
            llm.model,
        )
    invalid = [r.wellbore for r in results if not r.valid]
    logger.info(
        "run %s: %d wellbore(s), %d not valid %s", run_id, len(results), len(invalid), invalid or ""
    )
    return 1 if invalid else 0
