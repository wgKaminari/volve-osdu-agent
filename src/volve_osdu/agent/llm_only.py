"""The "llm_only" baseline (guide 8.1): one prompt per wellbore with the extracted text, the LLM
answers everything at once. No retrieval, no reference lookup, no retries.

The shared pipeline still runs every validator afterwards (including rule 8, which drops
ungrounded facts), so the comparison isolates what the agent's graph adds: focused prompts,
verification feedback and retries. Inputs are capped to fit an 8k-token local context; what is cut
is reported in stats.json.
"""

import logging

from pydantic import BaseModel, ValidationError

from volve_osdu.agent.graph import NULL_CODES, PDF_FACTS, CurveOut, PdfFactOut, parse_reply
from volve_osdu.agent.llm import CachedLLM
from volve_osdu.agent.prompting import load_prompt
from volve_osdu.agent.tools import exists, reference_codes
from volve_osdu.config import relative
from volve_osdu.extract.curves import CurveMapping
from volve_osdu.extract.names import normalize_wellbore_name, short_to_full
from volve_osdu.facts import Fact, Provenance, ReviewFlag
from volve_osdu.ingest.inventory import Inventory
from volve_osdu.pipeline import Judgement

logger = logging.getLogger(__name__)
MAX_CURVES = 60
MAX_REPORT_CHARS = 7000
HEADER_ITEMS = ("WELL", "UWI", "COMP", "FLD", "LAT", "LON", "ELEV", "ELEV_TYPE", "STRT", "STOP")


class LlmOnlyOut(BaseModel):
    wellbore_name: str | None = None
    facts: list[PdfFactOut] = []
    curves: list[CurveOut] = []


class LlmOnlySystem:
    name = "llm_only"

    def __init__(self, llm: CachedLLM) -> None:
        self.llm = llm

    def __call__(self, inv: Inventory, parsed: list[Fact]) -> Judgement:
        start = len(self.llm.trace)
        prompt = load_prompt("llm_only_v1")
        headers = "\n".join(
            f"{log.path.name}: "
            + ", ".join(f"{k}={log.header_value(k)}" for k in HEADER_ITEMS if log.header_value(k))
            for log in inv.logs
        )
        curves: dict[str, tuple[str, str, str]] = {}
        for log in inv.logs:
            for c in log.curves:
                curves.setdefault(c.mnemonic, (c.mnemonic, c.unit, c.description))
        listed = list(curves.values())[:MAX_CURVES]
        report = ""
        if inv.pdf is not None:
            report = "\n".join(f"=== page {p.number} ===\n{p.text}" for p in inv.pdf.pages)
        folder = inv.logs[0].path.parent.name if inv.logs else ""
        messages = prompt.messages(
            folder=folder,
            headers=headers,
            curves="\n".join(" | ".join(c) for c in listed),
            report=report[:MAX_REPORT_CHARS],
        )
        flags: list[ReviewFlag] = []
        try:
            reply = self.llm.complete(messages, node="llm_only", prompt_version=prompt.version)
            out = parse_reply(reply, LlmOnlyOut)
            assert isinstance(out, LlmOnlyOut)
        except (ValueError, ValidationError) as exc:
            logger.warning("llm_only reply unusable: %s", exc)
            out = LlmOnlyOut()
            flags.append(
                ReviewFlag(
                    severity="warn",
                    fact="llm_only",
                    reason="unparseable",
                    message=f"reply not usable: {str(exc)[:200]}",
                )
            )

        name = normalize_wellbore_name(out.wellbore_name) if out.wellbore_name else None
        wellbore = None
        if name:
            wellbore = Fact(
                name="wellbore_name",
                value=name,
                provenance=[
                    Provenance(
                        source_file=folder,
                        locator="llm_only answer",
                        method="llm_extracted",
                        model=self.llm.model,
                        prompt_version=prompt.version,
                    )
                ],
            )
        facts = []
        for item in out.facts:
            if item.name not in PDF_FACTS or inv.pdf is None:
                continue
            value: float | str = item.value
            if item.name == "kickoff_wellbore_name":
                value = short_to_full(str(item.value)) or str(item.value)
            else:
                try:
                    value = float(item.value)
                except ValueError:
                    continue
            facts.append(
                Fact(
                    name=item.name,
                    value=value,
                    unit=PDF_FACTS[item.name],
                    provenance=[
                        Provenance(
                            source_file=relative(inv.pdf.path),
                            locator=f"PDF:p{item.page}",
                            method="llm_extracted",
                            quote=item.quote,
                            model=self.llm.model,
                            prompt_version=prompt.version,
                        )
                    ],
                )
            )
        answers = {c.mnemonic: c for c in out.curves}
        method = f"llm {self.llm.model} {prompt.version}"
        mappings: dict[str, list[CurveMapping]] = {}
        for log in inv.logs:
            mappings[log.path.name] = []
            for c in log.curves:
                answer = answers.get(c.mnemonic)
                if answer is None:
                    continue
                mappings[log.path.name].append(
                    CurveMapping(
                        c.mnemonic,
                        _valid("UnitOfMeasure", answer.unit_code),
                        _valid("LogCurveFamily", answer.family),
                        method=method,
                    )
                )
        names = [f for f in parsed if f.name == "wellbore_name"]
        aliases = [(p.quote or str(f.value), p) for f in names for p in f.provenance]
        return Judgement(
            wellbore_name=wellbore,
            aliases=aliases,
            facts=facts,
            mappings=mappings,
            flags=flags,
            trace=self.llm.trace[start:],
            stats={
                "curves_listed": len(listed),
                "curves_total": len(curves),
                "report_chars_sent": min(len(report), MAX_REPORT_CHARS),
                "report_chars_total": len(report),
            },
        )


def _valid(kind: str, code: str | None) -> str | None:
    """Keep a code only if it exists. No suggestions, no retry: that is what the agent adds."""
    if code is None or code.strip().upper() in NULL_CODES:
        return None
    if exists(kind, code):
        return code
    return {c.lower(): c for c in reference_codes(kind)}.get(code.lower())
