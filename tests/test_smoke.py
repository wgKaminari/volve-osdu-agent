"""Smoke test: the package imports and the CLI parses its arguments."""

import pytest

import volve_osdu.cli


def test_cli_requires_a_command() -> None:
    with pytest.raises(SystemExit) as exc:
        volve_osdu.cli.main([])
    assert exc.value.code == 2


def test_cli_help_lists_run() -> None:
    with pytest.raises(SystemExit) as exc:
        volve_osdu.cli.main(["run", "--help"])
    assert exc.value.code == 0
