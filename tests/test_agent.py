"""Tests for the agent graph with a fake LLM: grounding, retries with feedback, cache, trace."""

import json
from pathlib import Path

import pytest

from conftest import FIXTURES
from volve_osdu.agent.graph import Agent
from volve_osdu.agent.llm import CachedLLM, FakeBackend, Messages
from volve_osdu.extract.parsed import las_facts
from volve_osdu.ingest.inventory import Inventory
from volve_osdu.ingest.las import read_las
from volve_osdu.ingest.pdf import PdfDocument, PdfPage

REFERENCE = FIXTURES.parent.parent / "data" / "raw" / "reference"
pytestmark = pytest.mark.skipif(not REFERENCE.exists(), reason="reference data not downloaded")

REPORT = PdfDocument(
    path=Path("report.pdf"),
    pages=[PdfPage(3, "2 Summary 15/9-F-12 was drilled to TD @ 3520 m MD RKB in Hugin Fm.")],
)


def scripted(replies: dict[str, list[dict]]) -> FakeBackend:
    """Reply per node (recognized from the system prompt), one scripted reply per attempt."""
    seen: dict[str, int] = {}

    def respond(messages: Messages) -> str:
        system = messages[0]["content"]
        node = (
            "identity" if "identify" in system else "pdf" if "petrophysical" in system else "curves"
        )
        i = seen.get(node, 0)
        seen[node] = i + 1
        options = replies[node]
        return json.dumps(options[min(i, len(options) - 1)])

    return FakeBackend(respond)


IDENTITY = {"wellbore_name": "15/9-F-12", "quote": "NO 15/9-F-12", "source": "sample.las UWI"}
GOOD_TD = {"facts": [{"name": "td_md_m", "value": 3520, "page": 3, "quote": "TD @ 3520 m MD RKB"}]}
CURVES = {
    "curves": [
        {"mnemonic": "GR", "unit_code": "gAPI", "family": "Gamma Ray"},
        {"mnemonic": "RHOB", "unit_code": "g/cm3", "family": "Bulk Density"},
    ]
}


def inventory() -> tuple[Inventory, list]:
    log = read_las(FIXTURES / "sample.las")
    return Inventory(logs=[log], pdf=REPORT, wellpath=None), las_facts(log)[0]


def run(backend: FakeBackend, tmp_path: Path) -> tuple[dict, CachedLLM]:
    llm = CachedLLM(backend, cache_dir=tmp_path / "cache")
    inv, parsed = inventory()
    return Agent(llm).run(inv, parsed), llm


def test_happy_path_is_grounded_and_traced(tmp_path: Path) -> None:
    state, llm = run(
        scripted({"identity": [IDENTITY], "pdf": [GOOD_TD], "curves": [CURVES]}), tmp_path
    )
    assert state["wellbore_name"].value == "15/9-F-12"
    assert state["wellbore_name"].provenance[0].method == "llm_extracted"
    td = state["pdf_facts"][0]
    assert (td.value, td.provenance[0].locator, td.provenance[0].quote) == (
        3520.0,
        "PDF:p3",
        "TD @ 3520 m MD RKB",
    )
    assert state["mappings"]["sample.las"]["GR"].family == "Gamma Ray"
    assert [t["node"] for t in llm.trace] == ["identity", "pdf_facts", "curves"]
    assert all({"prompt_tokens", "completion_tokens", "latency_s"} <= t.keys() for t in llm.trace)


def test_hallucinated_quote_is_rejected_then_fixed_on_retry(tmp_path: Path) -> None:
    invented = {
        "facts": [{"name": "td_md_m", "value": 3600, "page": 3, "quote": "TD @ 3600 m MD RKB"}]
    }
    backend = scripted({"identity": [IDENTITY], "pdf": [invented, GOOD_TD], "curves": [CURVES]})
    state, llm = run(backend, tmp_path)
    assert [f.value for f in state["pdf_facts"]] == [3520.0]
    retry = [t for t in llm.trace if t["node"] == "pdf_facts"]
    assert len(retry) == 2
    assert state["flags"] == []  # the rejected value was fixed, nothing left to review


def test_persistently_ungrounded_fact_is_dropped_and_flagged(tmp_path: Path) -> None:
    invented = {"facts": [{"name": "kop_md_m", "value": 1000, "page": 3, "quote": "KOP @ 1000 m"}]}
    state, llm = run(
        scripted({"identity": [IDENTITY], "pdf": [invented], "curves": [CURVES]}), tmp_path
    )
    assert state["pdf_facts"] == []
    assert [t["node"] for t in llm.trace].count("pdf_facts") == 3  # 1 try + 2 retries
    assert any(f.reason == "ungrounded" and f.fact == "kop_md_m" for f in state["flags"])


def test_invented_curve_family_gets_suggestions_and_retry(tmp_path: Path) -> None:
    wrong = {
        "curves": [
            {"mnemonic": "GR", "unit_code": "gAPI", "family": "GammaRay"},
            {"mnemonic": "RHOB", "unit_code": "g/cm3", "family": "Bulk Density"},
        ]
    }
    prompts: list[str] = []
    base = scripted({"identity": [IDENTITY], "pdf": [GOOD_TD], "curves": [wrong, CURVES]})

    def spy(messages: Messages) -> str:
        prompts.append(messages[1]["content"])
        return base.respond(messages)

    state, _ = run(FakeBackend(spy), tmp_path)
    assert state["mappings"]["sample.las"]["GR"].family == "Gamma Ray"
    assert any("'GammaRay' does not exist; closest: 'Gamma Ray'" in p for p in prompts)


def test_identity_without_supporting_quote_abstains(tmp_path: Path) -> None:
    invented = {"wellbore_name": "15/9-F-14", "quote": "15/9-F-14", "source": "made up"}
    state, _ = run(
        scripted({"identity": [invented], "pdf": [GOOD_TD], "curves": [CURVES]}), tmp_path
    )
    assert state["wellbore_name"] is None
    assert any(f.fact == "wellbore_name" and f.reason == "ungrounded" for f in state["flags"])


def test_second_run_is_served_from_cache(tmp_path: Path) -> None:
    replies = {"identity": [IDENTITY], "pdf": [GOOD_TD], "curves": [CURVES]}
    _, first = run(scripted(replies), tmp_path)
    second_backend = scripted(replies)
    _, second = run(second_backend, tmp_path)
    assert first.api_calls == 3
    assert second.api_calls == 0 and second_backend.calls == 0
    assert all(t["cached"] for t in second.trace)
