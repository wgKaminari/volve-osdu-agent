"""`volve-osdu eval`: run every system on the 13 real and the perturbed bundles, score, report.

Runs go to outputs/eval-<system>/{real,perturbed}/. LLM systems are served from the disk cache
after their first run, so re-running the evaluation reproduces docs/results.md exactly.
"""

import logging
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from volve_osdu.config import ROOT, Bundle, load_bundles, namespace
from volve_osdu.eval import metrics as m
from volve_osdu.eval.conflicts import detections, expected, load_conflicts
from volve_osdu.eval.perturb import PERTURBATIONS, build
from volve_osdu.eval.predictions import Prediction, read_prediction
from volve_osdu.pipeline import System, run_wellbore

logger = logging.getLogger(__name__)
OUTPUTS = ROOT / "outputs"


@dataclass
class SystemResult:
    name: str
    model: str | None
    real: dict[str, Prediction]  # canonical name -> prediction
    perturbed: dict[str, Prediction]  # perturbation id -> prediction
    outcomes: list[m.Outcome] = field(default_factory=list)
    api_calls: int = 0


def make_system(name: str) -> tuple[str | System, Any]:
    if name == "rules":
        return "rules", None
    from volve_osdu.agent.llm import from_env
    from volve_osdu.agent.llm_only import LlmOnlySystem
    from volve_osdu.agent.system import AgentSystem

    llm = from_env()
    return (AgentSystem(llm) if name == "agent" else LlmOnlySystem(llm)), llm


def load_system(name: str, bundles: list[Bundle]) -> SystemResult:
    """Re-score an earlier run from its output folders (no system is run, no LLM is called)."""
    root = OUTPUTS / f"eval-{name}"
    real = {b.canonical_name: read_prediction(root / "real" / b.folder.name) for b in bundles}
    perturbed = {p.id: read_prediction(root / "perturbed" / p.id) for p in PERTURBATIONS}
    models = {t["model"] for pred in real.values() for t in pred.trace}
    return SystemResult(name, ", ".join(sorted(models)) or None, real, perturbed)


def run_system(name: str, bundles: list[Bundle]) -> SystemResult:
    system, llm = make_system(name)
    root = OUTPUTS / f"eval-{name}"
    real = {}
    for bundle in bundles:
        result = run_wellbore(bundle, system, root / "real", namespace())
        real[bundle.canonical_name] = read_prediction(result.out_dir)
    perturbed = {}
    for p in PERTURBATIONS:
        result = run_wellbore(build(p), system, root / "perturbed", namespace())
        perturbed[p.id] = read_prediction(result.out_dir)
    return SystemResult(
        name, llm.model if llm else None, real, perturbed, api_calls=llm.api_calls if llm else 0
    )


def score(result: SystemResult, bundles: list[Bundle]) -> None:
    gold, labels = m.load_header_gold(), m.load_curve_labels()
    for bundle in bundles:
        pred = result.real[bundle.canonical_name]
        result.outcomes += m.score_fields(bundle.canonical_name, pred, gold)
        result.outcomes += m.score_curves(bundle.canonical_name, bundle, pred, labels)


def summarize(result: SystemResult, bundles: list[Bundle]) -> dict[str, Any]:
    o = result.outcomes
    s: dict[str, Any] = {
        "field_accuracy": m.ratio_with_ci(m.per_wellbore(o, "field")),
        "abstention_accuracy": m.ratio_with_ci(m.per_wellbore(o, "abstain")),
        "curve_unit_accuracy": m.ratio_with_ci(m.per_wellbore(o, "curve_unit")),
        "curve_family_accuracy": m.ratio_with_ci(m.per_wellbore(o, "curve_family")),
        "per_fact": {
            fact: m.ratio_with_ci(m.per_wellbore(o, "field", fact)) for fact in m.SCORED_FACTS
        },
        "operator_strict": m.ratio_with_ci(m.per_wellbore(o, "strict")),
    }

    # Grounding: llm_extracted report facts kept vs dropped (by the graph or by the pipeline).
    kept: dict[str, tuple[int, int]] = {}
    first: dict[str, tuple[int, int]] = {}
    halluc: dict[str, tuple[int, int]] = {}
    valid = {}
    for bundle in bundles:
        pred = result.real[bundle.canonical_name]
        n_kept = sum(
            1
            for f in pred.facts.values()
            if any(
                p.get("method") == "llm_extracted" and p.get("locator", "").startswith("PDF:")
                for p in f.get("provenance", [])
            )
        )
        n_dropped = sum(
            1 for f in pred.flags if f["reason"] == "ungrounded" and f["fact"] != "wellbore_name"
        )
        kept[bundle.canonical_name] = (n_kept, n_kept + n_dropped)
        g = pred.stats.get("grounding")
        if g:
            first[bundle.canonical_name] = (g["first_grounded"], g["first_proposed"])
        populated = [(f, v) for f, v in pred.values.items() if v is not None]
        bad = sum(m.hallucinated(bundle, f, v) for f, v in populated)
        halluc[bundle.canonical_name] = (bad, len(populated))
        valid[bundle.canonical_name] = (int(pred.valid), 1)
    s["grounding_final"] = m.ratio_with_ci(kept)
    s["grounding_first_attempt"] = m.ratio_with_ci(first)
    s["hallucination_rate"] = m.ratio_with_ci(halluc)
    s["validation_pass_rate"] = m.ratio_with_ci(valid)

    # Review flags vs conflicts.csv, on real + perturbed bundles; unit of resampling = bundle.
    conflicts = expected(load_conflicts())
    found: set[tuple[str, str, str]] = set()
    folders = {b.canonical_name: b.folder.name for b in bundles}
    for name, pred in result.real.items():
        found |= detections(folders[name], pred.flags)
    for pid, pred in result.perturbed.items():
        found |= detections(pid, pred.flags)
    by_bundle_p: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    by_bundle_r: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for d in found:
        n, t = by_bundle_p[d[0]]
        by_bundle_p[d[0]] = (n + int(d in conflicts), t + 1)
    for c in conflicts:
        n, t = by_bundle_r[c[0]]
        by_bundle_r[c[0]] = (n + int(c in found), t + 1)
    s["flag_precision"] = m.ratio_with_ci(dict(by_bundle_p))
    s["flag_recall"] = m.ratio_with_ci(dict(by_bundle_r))
    s["false_flags"] = sorted(found - conflicts)
    s["missed_conflicts"] = sorted(conflicts - found)

    traces = [t for p in result.real.values() for t in p.trace]
    n = len(bundles)
    s["llm"] = {
        "calls": len(traces),
        "calls_per_wellbore": len(traces) / n,
        "tokens_per_wellbore": sum(t["prompt_tokens"] + t["completion_tokens"] for t in traces) / n,
        "seconds_per_wellbore": sum(t["latency_s"] for t in traces) / n,
        "retries": sum(
            1
            for p in result.real.values()
            if p.stats.get("pdf_attempts", 0) > 1 or p.stats.get("curve_attempts", 0) > 1
        ),
        "api_calls_this_run": result.api_calls,
    }
    return s


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def evaluate(systems: list[str], report_path: Path, run: bool = True) -> list[SystemResult]:
    from volve_osdu.eval.report import write_report

    bundles = load_bundles()
    results = []
    for name in systems:
        logger.info("evaluating %s", name)
        result = run_system(name, bundles) if run else load_system(name, bundles)
        score(result, bundles)
        results.append(result)
    summaries = {r.name: summarize(r, bundles) for r in results}
    write_report(
        report_path,
        results,
        summaries,
        bundles,
        meta={"date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": git_commit()},
    )
    return results
