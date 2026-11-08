"""Known and injected conflicts (data/gold/conflicts.csv) and review-flag precision/recall."""

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from volve_osdu.config import ROOT
from volve_osdu.eval.perturb import PERTURBATIONS

CONFLICTS_CSV = ROOT / "data" / "gold" / "conflicts.csv"
# Flag reasons that claim "the inputs contain a problem". Flags about the system's own work
# (ungrounded, unmapped) or blanket notes (crs_assumed) are not conflict detections.
CONFLICT_REASONS = {
    "conflict",
    "log_below_survey",
    "log_below_td",
    "outside_volve",
    "plan_not_actual",
    "unit_converted",
    "kop_not_above_td",
}
DEPTH_REASONS = {"log_below_survey", "log_below_td"}  # one detection per bundle, any curve


@dataclass(frozen=True)
class Conflict:
    bundle: str  # output folder: real bundle folder (15_9-F12) or perturbation id (P03)
    wellbore: str
    fact: str
    reason: str
    kind: str  # "known" (real, in the inputs) or "injected"
    description: str


# Real conflicts in the Volve inputs, each checked by hand against the files (M1-M3).
KNOWN = [
    Conflict(
        "15_9-F12",
        "15/9-F-12",
        "*",
        "log_below_survey",
        "known",
        "WLC_PETRO_COMPUTED_INPUT_1.LAS GR reaches 4186.7 m MD; F-12_ACTUAL ends at 3520 m",
    ),
    Conflict(
        "15_9-19SR",
        "15/9-19 SR",
        "field_name",
        "conflict",
        "known",
        "159-19SR_LFP.las FLD=VOLVE vs STAT1990 composite LAS FLD=Q15",
    ),
    Conflict(
        "15_9-19SR",
        "15/9-19 SR",
        "operator_name",
        "conflict",
        "known",
        "159-19SR_LFP.las COMP=STATOIL PETROLEUM AS vs STAT1990 composite COMP=STATOIL",
    ),
]


def all_conflicts() -> list[Conflict]:
    rows = list(KNOWN)
    for p in PERTURBATIONS:
        if p.expected_reason is not None:
            rows.append(
                Conflict(
                    p.id,
                    p.wellbore,
                    p.expected_fact or "*",
                    p.expected_reason,
                    "injected",
                    p.description,
                )
            )
        # A perturbed copy keeps the real conflicts of its source bundle.
        for known in KNOWN:
            if known.wellbore == p.wellbore:
                rows.append(
                    Conflict(
                        p.id,
                        p.wellbore,
                        known.fact,
                        known.reason,
                        "known",
                        f"inherited from {known.bundle}: {known.description}",
                    )
                )
    return rows


def write_conflicts(path: Path = CONFLICTS_CSV) -> None:
    rows = all_conflicts()
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)


def load_conflicts(path: Path = CONFLICTS_CSV) -> list[Conflict]:
    with path.open() as f:
        return [Conflict(**row) for row in csv.DictReader(f)]


def detections(bundle: str, flags: list[dict]) -> set[tuple[str, str, str]]:
    """(bundle, fact, reason) for every conflict-type flag; depth flags collapse to fact "*"."""
    found = set()
    for flag in flags:
        reason = flag["reason"]
        if reason not in CONFLICT_REASONS:
            continue
        fact = "*" if reason in DEPTH_REASONS else flag["fact"]
        found.add((bundle, fact, reason))
    return found


def expected(conflicts: list[Conflict]) -> set[tuple[str, str, str]]:
    return {(c.bundle, c.fact, c.reason) for c in conflicts}
