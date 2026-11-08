"""The "agent" system: runs the graph and hands its decisions to the shared pipeline."""

from volve_osdu.agent.graph import Agent
from volve_osdu.agent.llm import CachedLLM
from volve_osdu.facts import Fact, Provenance
from volve_osdu.ingest.inventory import Inventory
from volve_osdu.pipeline import Judgement


class AgentSystem:
    name = "agent"

    def __init__(self, llm: CachedLLM) -> None:
        self.llm = llm
        self.agent = Agent(llm)

    def __call__(self, inv: Inventory, parsed: list[Fact]) -> Judgement:
        start = len(self.llm.trace)
        state = self.agent.run(inv, parsed)
        names = [f for f in parsed if f.name == "wellbore_name"]
        aliases: list[tuple[str, Provenance]] = [
            (p.quote or str(f.value), p) for f in names for p in f.provenance
        ]
        mappings = {
            file: list(by_mnemonic.values()) for file, by_mnemonic in state["mappings"].items()
        }
        return Judgement(
            wellbore_name=state.get("wellbore_name"),
            aliases=aliases,
            facts=state["pdf_facts"],
            mappings=mappings,
            flags=state["flags"],
            trace=self.llm.trace[start:],
            stats={
                "grounding": state["grounding"],
                "pdf_attempts": state["pdf_attempts"],
                "curve_attempts": state["curve_attempts"],
            },
        )
