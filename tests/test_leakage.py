"""Leakage audit (guide section 11): a run must never open gold, NPD headers or Well_picks.

A Python audit hook records every file opened while one wellbore runs end to end.
"""

import json
import sys
from pathlib import Path

import pytest

from volve_osdu.config import RAW, ROOT, find_bundle
from volve_osdu.pipeline import run_wellbore

pytestmark = pytest.mark.skipif(
    not (RAW / "spwla_volve").exists(), reason="raw data not downloaded"
)

FORBIDDEN = (
    str(ROOT / "data" / "gold"),
    str(RAW / "volve_field_data" / "input_data" / "wellheaders"),
    str(RAW / "spwla_volve" / "Well_picks_Volve_v1.dat"),
    str(RAW / "volve_field_data" / "input_data" / "lithostrat"),
)
_opened: list[str] = []
_recording = [False]


def _hook(event: str, args: tuple) -> None:
    if _recording[0] and event == "open" and isinstance(args[0], str | Path):
        _opened.append(str(Path(args[0]).resolve()))


sys.addaudithook(_hook)  # cannot be removed; it only records while _recording is set


def opened_during(run) -> list[str]:  # noqa: ANN001
    _opened.clear()
    _recording[0] = True
    try:
        run()
    finally:
        _recording[0] = False
    return list(_opened)


def test_rules_run_never_opens_gold(tmp_path: Path) -> None:
    files = opened_during(
        lambda: run_wellbore(find_bundle("15/9-F-12"), "rules", tmp_path, "volve")
    )
    assert any("WLC_PETRO_COMPUTED_INPUT_1.LAS" in f for f in files)  # the hook does see reads
    assert [f for f in files if f.startswith(FORBIDDEN)] == []


def test_agent_run_never_opens_gold(tmp_path: Path) -> None:
    from volve_osdu.agent.llm import CachedLLM, FakeBackend
    from volve_osdu.agent.system import AgentSystem

    def respond(messages: list[dict[str, str]]) -> str:
        if "identify" in messages[0]["content"]:
            return json.dumps({"wellbore_name": "15/9-F-1 A", "quote": "15/9-F-1 A"})
        return json.dumps({"facts": [], "curves": []})

    system = AgentSystem(CachedLLM(FakeBackend(respond), cache_dir=tmp_path / "cache"))
    files = opened_during(
        lambda: run_wellbore(find_bundle("15/9-F-1 A"), system, tmp_path, "volve")
    )
    assert any("PETROPHYSICAL_REPORT_1.PDF" in f for f in files)
    assert [f for f in files if f.startswith(FORBIDDEN)] == []
