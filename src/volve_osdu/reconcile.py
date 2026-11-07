"""Reconcile facts that several sources report (pipeline step 5, validation rule 9).

Values that agree within tolerance merge into one fact carrying every source. Values that don't
agree become a "conflict" review flag listing every candidate. The resolved value is the one with
strictly more supporting sources; on a tie we abstain (None) and leave it to the reviewer.
"""

import re
from collections import defaultdict

from volve_osdu.facts import Fact, ReviewFlag

# PROJECT_GUIDE.md section 7, rule 9.
TOLERANCES = {"kb_elevation_m": 0.2}
DEPTH_TOLERANCE_M = 0.5
ANGLE_TOLERANCE_DEG = 1e-4


def tolerance(fact_name: str) -> float:
    if fact_name in TOLERANCES:
        return TOLERANCES[fact_name]
    if fact_name.endswith("_deg"):
        return ANGLE_TOLERANCE_DEG
    return DEPTH_TOLERANCE_M


def same_value(name: str, a: float | str | None, b: float | str | None) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= tolerance(name)
    return _norm(a) == _norm(b)


def reconcile(facts: list[Fact]) -> tuple[dict[str, Fact], list[ReviewFlag]]:
    by_name: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.value is not None:
            by_name[fact.name].append(fact)

    resolved: dict[str, Fact] = {}
    flags: list[ReviewFlag] = []
    for name, group in by_name.items():
        clusters: list[Fact] = []
        for fact in group:
            for cluster in clusters:
                if same_value(name, cluster.value, fact.value):
                    cluster.provenance.extend(fact.provenance)
                    break
            else:
                clusters.append(fact.model_copy(deep=True))

        if len(clusters) == 1:
            resolved[name] = clusters[0]
            continue

        clusters.sort(key=lambda c: len(c.provenance), reverse=True)
        winner = clusters[0] if len(clusters[0].provenance) > len(clusters[1].provenance) else None
        values = ", ".join(f"{c.value!r} ({len(c.provenance)} source(s))" for c in clusters)
        flags.append(
            ReviewFlag(
                severity="warn",
                fact=name,
                reason="conflict",
                message=f"sources disagree on {name}: {values}; "
                + (f"kept {winner.value!r} (majority)" if winner else "left empty (tie)"),
                candidates=clusters,
            )
        )
        resolved[name] = winner or Fact(name=name, value=None, unit=clusters[0].unit)
    return resolved, flags


def _norm(value: float | str | None) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()
