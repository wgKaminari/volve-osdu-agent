"""Metrics (PROJECT_GUIDE.md section 8.2) and bootstrap confidence intervals over wellbores.

Every metric is a pooled ratio (correct / total). Its 95% CI comes from resampling *wellbores*
with replacement (2,000 resamples, percentile method), because values from one wellbore are not
independent (they share files). With n = 13 the intervals are wide; that is the honest picture.
"""

import csv
import random
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from volve_osdu.config import ROOT, Bundle
from volve_osdu.eval.gold import OPERATOR_ALIASES
from volve_osdu.eval.predictions import Prediction
from volve_osdu.ingest.las import read_las
from volve_osdu.ingest.pdf import read_pdf

GOLD = ROOT / "data" / "gold"
TOLERANCE = {
    "kb_elevation_m": 0.2,
    "td_md_m": 0.5,
    "kop_md_m": 0.5,
    "latitude": 1e-4,
    "longitude": 1e-4,
}
SCORED_FACTS = [
    "wellbore_name",
    "kb_elevation_m",
    "td_md_m",
    "kop_md_m",
    "latitude",
    "longitude",
    "operator",
    "field",
]
BOOTSTRAP_RESAMPLES = 2000


@dataclass(frozen=True)
class Outcome:
    """One scored unit. `kind` is "field", "abstain", "disputed", "curve_unit", "curve_family"."""

    wellbore: str
    fact: str
    kind: str
    gold: str | None
    predicted: float | str | None
    correct: bool | None  # None for disputed rows (reported, not scored)
    note: str = ""


# --- gold ---------------------------------------------------------------------------------


def load_header_gold(path: Path = GOLD / "wellbore_headers.csv") -> dict[tuple[str, str], dict]:
    with path.open() as f:
        return {(r["wellbore"], r["fact"]): r for r in csv.DictReader(f)}


def load_curve_labels(path: Path = GOLD / "curve_labels.csv") -> dict[tuple[str, str], dict]:
    with path.open() as f:
        return {(r["mnemonic"], r["las_unit"]): r for r in csv.DictReader(f)}


# --- scoring ------------------------------------------------------------------------------


def same(fact: str, predicted: float | str | None, gold: str) -> bool:
    if predicted is None:
        return False
    if fact in TOLERANCE:
        return (
            isinstance(predicted, int | float)
            and abs(float(predicted) - float(gold)) <= TOLERANCE[fact]
        )
    if fact == "operator":
        group = _alias_group(gold)
        return _norm(predicted) == _norm(gold) or (
            group is not None and _alias_group(predicted) == group
        )
    return _norm(predicted) == _norm(gold)


def score_fields(
    wellbore: str, pred: Prediction, gold: dict[tuple[str, str], dict]
) -> list[Outcome]:
    outcomes = [
        # Every MVP wellbore has a name in NPD or Well_picks; canonical_name in wells.yaml is it.
        Outcome(
            wellbore,
            "wellbore_name",
            "field",
            wellbore,
            pred.values["wellbore_name"],
            _norm(pred.values["wellbore_name"]) == _norm(wellbore),
        )
    ]
    for fact in SCORED_FACTS[1:]:
        row = gold.get((wellbore, fact))
        if row is None:
            continue  # no NPD header (15/9-19 BT2, 15/9-F-11 T2): only the name is scored
        value = row["value"] or None
        predicted = pred.values[fact]
        if row["disputed"] == "True":
            outcomes.append(
                Outcome(wellbore, fact, "disputed", value, predicted, None, row["note"])
            )
        elif row["recoverable"] == "True":
            assert value is not None
            outcomes.append(
                Outcome(wellbore, fact, "field", value, predicted, same(fact, predicted, value))
            )
            if fact == "operator":
                outcomes.append(
                    Outcome(
                        wellbore,
                        "operator_strict",
                        "strict",
                        value,
                        predicted,
                        _norm(predicted) == _norm(value),
                    )
                )
        else:
            outcomes.append(
                Outcome(
                    wellbore,
                    fact,
                    "abstain",
                    value,
                    predicted,
                    predicted is None,
                    row["recoverable_note"],
                )
            )
    return outcomes


def score_curves(
    wellbore: str, bundle: Bundle, pred: Prediction, labels: dict[tuple[str, str], dict]
) -> list[Outcome]:
    outcomes = []
    for path in bundle.las:
        las_units = {c.mnemonic: c.unit for c in _las(path).curves}
        for mnemonic, uom, family in pred.curves.get(path.name, []):
            label = labels.get((mnemonic, las_units.get(mnemonic, "")))
            if label is None:
                continue
            note = "reviewed" if label["reviewed"] == "true" else "unreviewed"
            gold_uom, gold_family = label["uom_code"] or None, label["family"] or None
            outcomes.append(
                Outcome(
                    wellbore,
                    f"{path.name}:{mnemonic}",
                    "curve_unit",
                    gold_uom,
                    uom,
                    uom == gold_uom,
                    note,
                )
            )
            outcomes.append(
                Outcome(
                    wellbore,
                    f"{path.name}:{mnemonic}",
                    "curve_family",
                    gold_family,
                    family,
                    family == gold_family,
                    note,
                )
            )
    return outcomes


def hallucinated(bundle: Bundle, fact: str, value: float | str | None) -> bool:
    """A populated value that appears nowhere in the bundle's input text (within tolerance)."""
    if value is None:
        return False
    key = (tuple(bundle.las), bundle.pdf)
    if isinstance(value, int | float):
        tol = TOLERANCE.get(fact, 0.5)
        return not any(abs(n - float(value)) <= tol for n in _numbers(*key))
    return _norm(value) not in _norm(_corpus(*key))


# --- statistics ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimate:
    value: float | None
    low: float | None
    high: float | None
    n_units: int  # wellbores contributing
    numerator: int
    denominator: int

    def fmt(self, pct: bool = True) -> str:
        if self.value is None:
            return "n/a"
        f = (lambda x: f"{100 * x:.0f}%") if pct else (lambda x: f"{x:.2f}")
        return (
            f"{f(self.value)} [{f(self.low)}, {f(self.high)}] ({self.numerator}/{self.denominator})"  # type: ignore[arg-type]
        )


def ratio_with_ci(per_wellbore: dict[str, tuple[int, int]], seed: int = 0) -> Estimate:
    """Pooled ratio sum(num)/sum(den) with a wellbore-level bootstrap 95% percentile CI."""
    units = [(n, d) for n, d in per_wellbore.values() if d > 0]
    num, den = sum(n for n, _ in units), sum(d for _, d in units)
    if den == 0:
        return Estimate(None, None, None, 0, 0, 0)
    rng = random.Random(seed)
    stats = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [units[rng.randrange(len(units))] for _ in units]
        d = sum(x[1] for x in sample)
        stats.append(sum(x[0] for x in sample) / d)
    stats.sort()
    low = stats[int(0.025 * BOOTSTRAP_RESAMPLES)]
    high = stats[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    return Estimate(num / den, low, high, len(units), num, den)


def per_wellbore(
    outcomes: list[Outcome], kind: str, fact: str | None = None
) -> dict[str, tuple[int, int]]:
    counts: dict[str, tuple[int, int]] = {}
    for o in outcomes:
        if o.kind != kind or (fact is not None and o.fact != fact) or o.correct is None:
            continue
        n, d = counts.get(o.wellbore, (0, 0))
        counts[o.wellbore] = (n + int(o.correct), d + 1)
    return counts


# --- helpers ------------------------------------------------------------------------------


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold() if value is not None else ""


def _alias_group(name: object) -> str | None:
    norm = _norm(name)
    return next((group for group, names in OPERATOR_ALIASES.items() if norm in names), None)


@cache
def _las(path: Path):  # noqa: ANN202
    return read_las(path)


@cache
def _corpus(las: tuple[Path, ...], pdf: Path | None) -> str:
    """All header text and report text of a bundle: what any system could have read."""
    parts = []
    for path in las:
        parts += [f"{item.mnemonic} {item.value}" for item in _las(path).well.values()]
    if pdf and pdf.is_file():
        parts += [p.text for p in read_pdf(pdf).pages]
    return "\n".join(parts)


@cache
def _numbers(las: tuple[Path, ...], pdf: Path | None) -> tuple[float, ...]:
    return tuple(float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", _corpus(las, pdf)))
