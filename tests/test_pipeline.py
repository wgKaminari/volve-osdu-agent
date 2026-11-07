"""End-to-end test: 15/9-F-12 with the rules system (M1 acceptance, PROJECT_GUIDE.md section 9)."""

import json
from pathlib import Path

import pytest

from volve_osdu.config import RAW, find_bundle
from volve_osdu.ingest.inventory import scan_wellpaths
from volve_osdu.pipeline import run_wellbore

pytestmark = pytest.mark.skipif(
    not (RAW / "spwla_volve").exists(), reason="raw data not downloaded"
)


@pytest.fixture(scope="module")
def f12(tmp_path_factory: pytest.TempPathFactory) -> Path:
    result = run_wellbore(
        find_bundle("15/9-F-12"), "rules", tmp_path_factory.mktemp("run"), "volve"
    )
    assert result.valid, [i for i in result.issues if i.severity == "error"]
    return result.out_dir


def test_f12_writes_a_valid_manifest_and_all_outputs(f12: Path) -> None:
    manifest = json.loads((f12 / "manifest.json").read_text())
    kinds = [r["kind"].split(":")[2] for r in manifest["MasterData"]]
    assert kinds == [
        "master-data--Organisation",
        "master-data--Field",
        "master-data--Well",
        "master-data--Wellbore",
    ]
    assert len(manifest["Data"]["WorkProductComponents"]) == 3  # 2 WellLogs + 1 trajectory
    assert len(list((f12 / "bulk").glob("*.parquet"))) == 3
    for name in ("provenance.json", "facts.json", "validation.json", "review.md"):
        assert (f12 / name).is_file()


def test_f12_review_shows_gr_below_final_survey(f12: Path) -> None:
    flags = json.loads((f12 / "validation.json").read_text())["flags"]
    gr = [f for f in flags if f["reason"] == "log_below_survey"]
    assert len(gr) == 1
    assert "GR has data down to 4186.7 m MD" in gr[0]["message"]
    assert "3520.0 m MD" in gr[0]["message"]
    assert "GR has data down to 4186.7" in (f12 / "review.md").read_text()


def test_plan_and_prototype_well_paths_are_excluded() -> None:
    actual, plans = scan_wellpaths(RAW / "volve_field_data" / "input_data" / "wellpaths")
    assert sorted(p.name for p in plans) == [
        "F-10 A rev#6 PROTOTYPE",
        "F-9A Utsira Water injector Rev10 PLAN",
    ]
    assert all("ACTUAL" in p.name for p in actual)


def test_agent_system_runs_end_to_end_with_a_fake_llm(tmp_path: Path) -> None:
    from volve_osdu.agent.llm import CachedLLM, FakeBackend
    from volve_osdu.agent.system import AgentSystem

    def respond(messages: list[dict[str, str]]) -> str:
        system, user = messages[0]["content"], messages[1]["content"]
        if "identify" in system:
            return json.dumps({"wellbore_name": "15/9-F-12", "quote": "NO 15/9-F-12"})
        if "petrophysical" in system:
            return json.dumps({"facts": []})
        mnemonics = [line.split(" | ")[0] for line in user.splitlines() if " | " in line][1:]
        return json.dumps(
            {"curves": [{"mnemonic": m, "unit_code": None, "family": None} for m in mnemonics]}
        )

    llm = CachedLLM(FakeBackend(respond), cache_dir=tmp_path / "cache")
    result = run_wellbore(find_bundle("15/9-F-12"), AgentSystem(llm), tmp_path / "out", "volve")
    assert result.valid
    trace = (result.out_dir / "trace.jsonl").read_text().splitlines()
    assert {json.loads(line)["node"] for line in trace} >= {"identity", "curves"}
    assert any(f.reason == "log_below_survey" for f in result.flags)
