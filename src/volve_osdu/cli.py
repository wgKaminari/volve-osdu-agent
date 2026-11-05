"""Command-line entry point (`volve-osdu`). Subcommands `run` and `eval` arrive in M1-M3."""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("volve-osdu: nothing here yet")
