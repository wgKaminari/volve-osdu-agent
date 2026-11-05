"""Smoke test: the package imports and the CLI entry point runs."""

import volve_osdu.cli


def test_cli_main_runs() -> None:
    volve_osdu.cli.main()
