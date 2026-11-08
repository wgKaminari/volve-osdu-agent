"""The agent: a LangGraph graph for the judgement steps of one wellbore (guide section 6).

    START -> identity -> pdf_facts -> curves -> check --retry--> pdf_facts ...
                                                  \\--done--> END

identity   LLM picks the wellbore name from header/folder/report evidence; checked against it.
pdf_facts  LLM extracts TD, KOP, kick-off parent and KB from the report, each with a verbatim
           quote; rule 8 (grounding) rejects anything not literally in the page text.
curves     LLM maps each curve to an OSDU unit code and LogCurveFamily; codes are checked against
           the pinned reference lists, near-misses get lookup_reference suggestions.
check      sends the specific problems back to the node that made them (max 2 retries), then
           drops what is still wrong and raises review flags.

Numbers never come from the LLM unless quoted from the source and verified by code. Records,
reconciliation and every other validation rule run afterwards in pipeline.py, shared with the
rules baseline.
"""

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

from volve_osdu.agent.llm import CachedLLM
from volve_osdu.agent.prompting import load_prompt
from volve_osdu.agent.tools import exists, lookup_reference, reference_codes, search_pdf
from volve_osdu.config import relative
from volve_osdu.extract.curves import CurveMapping
from volve_osdu.extract.names import most_specific_name, normalize_wellbore_name, short_to_full
from volve_osdu.extract.pdf_rules import name_pattern
from volve_osdu.facts import Fact, Provenance, ReviewFlag
from volve_osdu.ingest.inventory import Inventory
from volve_osdu.ingest.pdf import normalize_whitespace
from volve_osdu.validate.grounding import check_grounding, semantic_problem

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3  # first try + 2 retries (guide 6.1)
NULL_CODES = {"", "NULL", "NONE", "UNKNOWN", "N/A"}  # models often spell "no value" as text
CURVE_BATCH = 25  # keeps prompt + reasoning inside an 8k context
PDF_FACTS = {"td_md_m": "m", "kop_md_m": "m", "kb_elevation_m": "m", "kickoff_wellbore_name": None}


class IdentityOut(BaseModel):
    wellbore_name: str | None
    quote: str = ""
    source: str = ""
    confidence: float | None = None


class PdfFactOut(BaseModel):
    name: str
    value: float | str
    page: int
    quote: str


class PdfFactsOut(BaseModel):
    facts: list[PdfFactOut]


class CurveOut(BaseModel):
    mnemonic: str
    unit_code: str | None = None
    family: str | None = None
    confidence: float | None = None


class CurvesOut(BaseModel):
    curves: list[CurveOut]


class State(TypedDict, total=False):
    inv: Inventory
    parsed: list[Fact]
    wellbore_name: Fact | None
    pdf_pending: bool
    pdf_feedback: str
    pdf_attempts: int
    pdf_facts: list[Fact]
    pdf_rejected: list[tuple[Fact, str]]
    grounding: dict[str, int]  # proposed / grounded counts, all attempts and first attempt
    curve_pending: dict[str, list[dict[str, str]]]  # file -> curves still to map
    curve_feedback: dict[str, str]
    curve_attempts: int
    mappings: dict[str, dict[str, CurveMapping]]
    flags: list[ReviewFlag]


def parse_reply(text: str, model: type[BaseModel]) -> BaseModel:
    """Parse the model's JSON reply; tolerate prose or code fences around the object."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("reply contains no JSON object")
    return model.model_validate(json.loads(text[start : end + 1]))


class Agent:
    def __init__(self, llm: CachedLLM) -> None:
        self.llm = llm
        # Identical curve lines (same mnemonic, unit, description) get the same mapping; the
        # three 15/9-19 LFP files share ~150 curves, so this avoids mapping them three times.
        self.memo: dict[tuple[str, str, str], CurveMapping] = {}
        graph = StateGraph(State)
        graph.add_node("identity", self.identity)
        graph.add_node("pdf_facts", self.pdf_facts)
        graph.add_node("curves", self.curves)
        graph.add_node("check", self.check)
        graph.add_edge(START, "identity")
        graph.add_edge("identity", "pdf_facts")
        graph.add_edge("pdf_facts", "curves")
        graph.add_edge("curves", "check")
        graph.add_conditional_edges("check", self.route, {"retry": "pdf_facts", "done": END})
        self.graph = graph.compile()

    def run(self, inv: Inventory, parsed: list[Fact]) -> State:
        pending = {
            log.path.name: [
                {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
                for c in log.curves
            ]
            for log in inv.logs
        }
        initial: State = {
            "inv": inv,
            "parsed": parsed,
            "pdf_pending": inv.pdf is not None,
            "pdf_feedback": "",
            "pdf_attempts": 0,
            "pdf_facts": [],
            "pdf_rejected": [],
            "grounding": {"proposed": 0, "grounded": 0, "first_proposed": 0, "first_grounded": 0},
            "curve_pending": pending,
            "curve_feedback": {},
            "curve_attempts": 0,
            "mappings": {name: {} for name in pending},
            "flags": [],
        }
        return self.graph.invoke(initial, {"recursion_limit": 25})  # type: ignore[return-value]

    # --- identity -------------------------------------------------------------------------

    def identity(self, state: State) -> dict[str, Any]:
        inv = state["inv"]
        evidence: list[tuple[str, str, Provenance]] = []
        for fact in state["parsed"]:
            if fact.name == "wellbore_name":
                for p in fact.provenance:
                    label = f"{p.source_file.rsplit('/', 1)[-1]} {p.locator.rsplit('/', 1)[-1]}"
                    evidence.append((label, p.quote or str(fact.value), p))
        for log in inv.logs:
            folder = log.path.parent
            evidence.append(
                (
                    "folder name",
                    folder.name,
                    Provenance(
                        source_file=relative(folder), locator="folder name", method="parsed"
                    ),
                )
            )
            break
        if inv.pdf is not None and inv.pdf.pages:
            title = normalize_whitespace(inv.pdf.pages[0].text)[:300]
            evidence.append(
                (
                    "report page 1",
                    title,
                    Provenance(
                        source_file=relative(inv.pdf.path), locator="PDF:p1", method="parsed"
                    ),
                )
            )
        prompt = load_prompt("identity_v1")
        lines = "\n".join(f"- {label}: {text}" for label, text, _ in evidence)
        flags: list[ReviewFlag] = []
        try:
            out = parse_reply(
                self.llm.complete(
                    prompt.messages(evidence=lines), node="identity", prompt_version=prompt.version
                ),
                IdentityOut,
            )
            assert isinstance(out, IdentityOut)
        except (ValueError, ValidationError) as exc:
            logger.warning("identity reply unusable: %s", exc)
            out = IdentityOut(wellbore_name=None)

        name = normalize_wellbore_name(out.wellbore_name) if out.wellbore_name else None
        support = [
            (label, text, p)
            for label, text, p in evidence
            if out.quote and normalize_whitespace(out.quote) in normalize_whitespace(text)
        ]
        grounded = bool(name and support and _quote_names(out.quote, name))
        if not grounded:
            # The LLM abstained or could not back its answer. Fall back to the deterministic
            # choice (most specific header name) so the wellbore is still built, and say so.
            fallback = most_specific_name([f for f in state["parsed"] if f.name == "wellbore_name"])
            answer = f"LLM answer {out.wellbore_name!r} (quote {out.quote!r}) not supported"
            if not out.wellbore_name:
                answer = "LLM abstained"
            flags.append(
                ReviewFlag(
                    severity="warn",
                    fact="wellbore_name",
                    reason="identity_fallback",
                    message=f"{answer}; used the most specific header name "
                    f"{fallback.value if fallback else None!r} instead",
                    candidates=[fallback] if fallback else [],
                )
            )
            return {"wellbore_name": fallback, "flags": state["flags"] + flags}

        provenance = [
            p.model_copy(
                update={
                    "method": "llm_extracted",
                    "quote": out.quote,
                    "model": self.llm.model,
                    "prompt_version": prompt.version,
                }
            )
            for _label, _text, p in support
        ]
        fact = Fact(
            name="wellbore_name", value=name, provenance=provenance, confidence=out.confidence
        )
        return {"wellbore_name": fact}

    # --- pdf facts --------------------------------------------------------------------------

    def pdf_facts(self, state: State) -> dict[str, Any]:
        inv, name = state["inv"], state.get("wellbore_name")
        if not state["pdf_pending"] or inv.pdf is None or name is None or name.value is None:
            return {"pdf_pending": False}
        pages = search_pdf(inv.pdf, str(name.value))
        if not pages:
            flag = ReviewFlag(
                severity="info",
                fact="report",
                reason="not_mentioned",
                message=f"{inv.pdf.path.name} never names {name.value}; no report facts",
            )
            return {"pdf_pending": False, "flags": state["flags"] + [flag]}

        prompt = load_prompt("pdf_facts_v1")
        text = "\n".join(f"=== page {p.number} ===\n{p.text}" for p in pages)
        feedback = state["pdf_feedback"]
        attempts = state["pdf_attempts"] + 1
        try:
            reply = self.llm.complete(
                prompt.messages(wellbore=str(name.value), feedback=feedback, pages=text),
                node="pdf_facts",
                prompt_version=prompt.version,
            )
            out = parse_reply(reply, PdfFactsOut)
            assert isinstance(out, PdfFactsOut)
        except (ValueError, ValidationError) as exc:
            return {
                "pdf_attempts": attempts,
                "pdf_pending": True,
                "pdf_feedback": f"Your previous reply was not valid JSON for the schema: {exc}",
            }

        accepted: dict[str, Fact] = {f.name: f for f in state["pdf_facts"]}
        rejected: list[tuple[Fact, str]] = []
        before = len(accepted)
        for item in out.facts:
            if item.name not in PDF_FACTS or item.name in accepted:
                continue
            value: float | str = item.value
            if PDF_FACTS[item.name] == "m":
                try:
                    value = float(item.value)
                except ValueError:
                    pass
            fact = Fact(
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
            checked, reason = check_grounding(fact, inv.pdf)
            if checked is None or (PDF_FACTS[item.name] == "m" and not isinstance(value, float)):
                rejected.append((fact, reason or "value is not a number"))
                continue
            if item.name == "kickoff_wellbore_name":
                full = short_to_full(str(value))
                if full is None:
                    rejected.append((fact, f"{value!r} is not a wellbore name"))
                    continue
                checked = checked.model_copy(update={"value": full})
            problem = semantic_problem(checked, str(name.value))
            if problem:
                rejected.append((fact, problem))
                continue
            accepted[item.name] = checked

        counts = dict(state["grounding"])
        proposed = len(accepted) - before + len(rejected)
        counts["proposed"] += proposed
        counts["grounded"] += len(accepted) - before
        if attempts == 1:
            counts["first_proposed"] = proposed
            counts["first_grounded"] = len(accepted) - before
        feedback = ""
        if rejected:
            feedback = (
                "Your previous answer had problems; fix them or leave the fact out:\n"
                + "\n".join(f"- {f.name} = {f.value!r}: {reason}" for f, reason in rejected)
            )
        return {
            "pdf_facts": list(accepted.values()),
            "pdf_rejected": rejected,
            "grounding": counts,
            "pdf_attempts": attempts,
            "pdf_pending": bool(rejected),
            "pdf_feedback": feedback,
        }

    # --- curves -----------------------------------------------------------------------------

    def curves(self, state: State) -> dict[str, Any]:
        if not state["curve_pending"]:
            return {}
        prompt = load_prompt("curve_mapping_v1")
        mappings = {k: dict(v) for k, v in state["mappings"].items()}
        pending: dict[str, list[dict[str, str]]] = {}
        feedback: dict[str, str] = {}
        method = f"llm {self.llm.model} {prompt.version}"
        for file, all_curves in state["curve_pending"].items():
            curves = []
            for curve in all_curves:
                known = self.memo.get(_curve_key(curve))
                if known is not None:
                    mappings[file][curve["mnemonic"]] = known
                else:
                    curves.append(curve)
            for i in range(0, len(curves), CURVE_BATCH):
                batch = curves[i : i + CURVE_BATCH]
                table = "\n".join(
                    f"{c['mnemonic']} | {c['unit']} | {c['description']}" for c in batch
                )
                try:
                    reply = self.llm.complete(
                        prompt.messages(
                            feedback=state["curve_feedback"].get(file, ""), curves=table
                        ),
                        node="curves",
                        prompt_version=prompt.version,
                    )
                    out = parse_reply(reply, CurvesOut)
                    assert isinstance(out, CurvesOut)
                    answers = {c.mnemonic: c for c in out.curves}
                except (ValueError, ValidationError) as exc:
                    pending.setdefault(file, []).extend(batch)
                    feedback[file] = f"Your previous reply was not valid JSON for the schema: {exc}"
                    continue
                notes = []
                for curve in batch:
                    answer = answers.get(curve["mnemonic"])
                    if answer is None:
                        pending.setdefault(file, []).append(curve)
                        notes.append(f"- {curve['mnemonic']}: missing from your reply")
                        continue
                    unit, unit_note = _check_code("UnitOfMeasure", answer.unit_code)
                    family, family_note = _check_code("LogCurveFamily", answer.family)
                    problems = [n for n in (unit_note, family_note) if n]
                    if problems:
                        pending.setdefault(file, []).append(curve)
                        notes.append(f"- {curve['mnemonic']}: " + "; ".join(problems))
                    else:
                        mapping = CurveMapping(curve["mnemonic"], unit, family, method=method)
                        mappings[file][curve["mnemonic"]] = mapping
                        self.memo[_curve_key(curve)] = mapping
                if notes:
                    feedback[file] = (
                        "Fix these curves (choose a suggestion or null):\n" + "\n".join(notes)
                    )
        return {
            "mappings": mappings,
            "curve_pending": pending,
            "curve_feedback": feedback,
            "curve_attempts": state["curve_attempts"] + 1,
        }

    # --- check / route ----------------------------------------------------------------------

    def check(self, state: State) -> dict[str, Any]:
        if self.route(state) == "retry":
            return {}
        flags = list(state["flags"])
        for fact, reason in state.get("pdf_rejected", []):
            flags.append(
                ReviewFlag(
                    severity="warn",
                    fact=fact.name,
                    reason="ungrounded",
                    message=f"dropped LLM value {fact.value!r}: {reason}",
                    candidates=[fact],
                )
            )
        for file, curves in state["curve_pending"].items():
            names = ", ".join(c["mnemonic"] for c in curves)
            flags.append(
                ReviewFlag(
                    severity="info",
                    fact="curve_mapping",
                    reason="unmapped",
                    message=f"{file}: no valid mapping after {MAX_ATTEMPTS} attempts for {names}",
                )
            )
        return {"flags": flags, "pdf_pending": False, "curve_pending": {}}

    @staticmethod
    def route(state: State) -> str:
        pdf_retry = state["pdf_pending"] and state["pdf_attempts"] < MAX_ATTEMPTS
        curve_retry = bool(state["curve_pending"]) and state["curve_attempts"] < MAX_ATTEMPTS
        return "retry" if pdf_retry or curve_retry else "done"


def _check_code(kind: str, code: str | None) -> tuple[str | None, str | None]:
    """(accepted code, problem). null is always acceptable: abstaining is allowed."""
    if code is None or code.strip().upper() in NULL_CODES:
        return None, None
    if exists(kind, code):
        return code, None
    by_lower = {c.lower(): c for c in reference_codes(kind)}
    if code.lower() in by_lower:  # same code, different capitalization: not a guess
        return by_lower[code.lower()], None
    suggestions = ", ".join(repr(s) for s in lookup_reference(kind, code))
    return None, f"{kind} {code!r} does not exist; closest: {suggestions}"


def _curve_key(curve: dict[str, str]) -> tuple[str, str, str]:
    """Curve identity without the running index some LAS writers prefix ("10  GR:...")."""
    description = re.sub(r"^\d+\s+", "", curve["description"].strip())
    return curve["mnemonic"], curve["unit"], description


def _quote_names(quote: str, name: str) -> bool:
    """The quote names exactly this wellbore ("15/9-F-1" must not pass on "15/9-F-1 A")."""
    if normalize_wellbore_name(quote) == name:
        return True
    text = re.sub(r"[_\s]+", " ", quote.upper())
    return re.search(name_pattern(name), text) is not None
