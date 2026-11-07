"""Business rules 2-7 and 10 (PROJECT_GUIDE.md section 7). Rule 1 is in schema.py, rule 9 in
reconcile.py, rule 8 (grounding) in grounding.py.

Structural problems become Issues (an "error" blocks ingestion). Things a human must judge, like
a log deeper than the well path, become ReviewFlags with every candidate value and its source.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from volve_osdu.config import REFERENCE_DIR, relative
from volve_osdu.facts import Fact, Issue, Provenance, ReviewFlag
from volve_osdu.ingest.las import LasLog
from volve_osdu.ingest.wellpath import WellPath
from volve_osdu.osdu.records import Record
from volve_osdu.osdu.reference import load_reference_ids

# A reference to another record: <ns>:<group>--<Type>:<code>:<version or empty>.
RECORD_REF = re.compile(
    r"^[\w\-.]+:(master-data|work-product-component|work-product|dataset)--[\w\-.]+:.+:[0-9]*$"
)
REFERENCE_DATA_REF = re.compile(r"^[\w\-.]+:reference-data--([\w\-.]+):.+:[0-9]*$")
REFERENCE_FILES = {
    "UnitOfMeasure": "UnitOfMeasure.1.json",
    "VerticalMeasurementType": "VerticalMeasurementType.1.json",
    "VerticalMeasurementPath": "VerticalMeasurementPath.1.json",
    "LogCurveType": "LogCurveType.1.json",
    "LogCurveFamily": "LogCurveFamily.1.json",
    "CoordinateReferenceSystem": "CoordinateReferenceSystem.1.json",
}

BELOW_SURVEY_TOLERANCE_M = 5.0
TVD_TOLERANCE_M = 0.01
VOLVE_BOX = {"lat": (58.40, 58.50), "lon": (1.80, 1.95)}


def walk(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (json path, leaf) pairs: "Curves[0].Mnemonic", "GR". Empty containers are leaves."""
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list) and value:
        for i, item in enumerate(value):
            yield from walk(item, f"{path}[{i}]")
    else:
        yield path, value


def rule2_references(records: list[Record]) -> list[Issue]:
    """Every record reference points to a record in this manifest."""
    ids = {r.id for r in records}
    issues = []
    for rec in records:
        for path, value in walk(rec.to_json()["data"]):
            if not isinstance(value, str) or not RECORD_REF.match(value):
                continue
            target = value.rsplit(":", 1)[0]
            if target in ids:
                continue
            outside = ":master-data--Wellbore:" in target and path == "KickOffWellbore"
            issues.append(
                Issue(
                    rule=2,
                    severity="info" if outside else "error",
                    record_id=rec.id,
                    path=path,
                    message=f"{target} is not in this manifest"
                    + (" (parent wellbore, loaded with its own manifest)" if outside else ""),
                )
            )
    return issues


def rule3_reference_values(
    records: list[Record], namespace: str, reference_dir: Path = REFERENCE_DIR
) -> list[Issue]:
    """Every reference-data ID exists in the pinned OSDU reference lists (catches invented IDs)."""
    issues = []
    for rec in records:
        for path, value in walk(rec.to_json()["data"]):
            if not isinstance(value, str):
                continue
            match = REFERENCE_DATA_REF.match(value)
            if not match:
                continue
            ref_type = match.group(1)
            file = REFERENCE_FILES.get(ref_type)
            if file is None:
                issues.append(
                    Issue(
                        rule=3,
                        severity="warn",
                        record_id=rec.id,
                        path=path,
                        message=f"no pinned list for {ref_type}; {value} not checked",
                    )
                )
            elif value not in load_reference_ids(reference_dir / file, namespace):
                issues.append(
                    Issue(
                        rule=3,
                        severity="error",
                        record_id=rec.id,
                        path=path,
                        message=f"{value} is not in the pinned {ref_type} list",
                    )
                )
    return issues


def rule4_depths(
    records: list[Record],
    logs: list[tuple[LasLog, float]],
    wellpath: WellPath | None,
    facts: dict[str, Fact],
) -> tuple[list[Issue], list[ReviewFlag]]:
    """Depth logic. `logs` pairs each LAS file with its depth-to-metres factor."""
    issues: list[Issue] = []
    flags: list[ReviewFlag] = []

    for rec in records:
        data = rec.data
        if rec.type == "WellLog":
            top, bottom = data.get("TopMeasuredDepth"), data.get("BottomMeasuredDepth")
            if top is not None and bottom is not None and top >= bottom:
                issues.append(
                    _depth_issue(rec, "TopMeasuredDepth", f"top {top} >= bottom {bottom}")
                )
            for i, curve in enumerate(data.get("Curves", [])):
                if curve.get("TopDepth", 0) > curve.get("BaseDepth", float("inf")):
                    issues.append(_depth_issue(rec, f"Curves[{i}]", "curve top below its base"))
        if rec.type == "WellboreTrajectory":
            top, base = data["TopDepthMeasuredDepth"], data["BaseDepthMeasuredDepth"]
            if top >= base:
                issues.append(
                    _depth_issue(rec, "TopDepthMeasuredDepth", f"top {top} >= base {base}")
                )

    kop, td = facts.get("kop_md_m"), facts.get("td_md_m")
    if kop and td and kop.value is not None and td.value is not None and kop.value >= td.value:
        flags.append(
            ReviewFlag(
                severity="warn",
                fact="kop_md_m",
                reason="kop_not_above_td",
                message=f"kick-off point {kop.value} m is not above TD {td.value} m",
                candidates=[kop, td],
            )
        )

    if wellpath is not None:
        md, tvd = wellpath.stations["md_m"], wellpath.stations["tvd_m"]
        if not md.is_monotonic_increasing or md.duplicated().any():
            issues.append(
                Issue(
                    rule=4,
                    severity="error",
                    record_id=None,
                    path=wellpath.path.name,
                    message="well path MD is not strictly increasing",
                )
            )
        bad = wellpath.stations[tvd > md + TVD_TOLERANCE_M]
        if len(bad):
            issues.append(
                Issue(
                    rule=4,
                    severity="error",
                    record_id=None,
                    path=wellpath.path.name,
                    message=f"TVD > MD at {len(bad)} station(s), first at MD {bad['md_m'].iloc[0]}",
                )
            )

    limits: list[Fact] = []
    if wellpath is not None and not wellpath.is_plan:
        limits.append(
            Fact(
                name="final_survey_md_m",
                value=wellpath.base_md,
                unit="m",
                provenance=[
                    Provenance(
                        source_file=relative(wellpath.path),
                        locator=f"WELLPATH:MD row {len(wellpath.stations) - 1}",
                        method="parsed",
                    )
                ],
            )
        )
    if td and td.value is not None:
        limits.append(td)
    for log, scale in logs:
        for curve in log.curves:
            if curve.base_depth is None:
                continue
            base = curve.base_depth * scale
            for limit in limits:
                assert isinstance(limit.value, float)
                if base <= limit.value + BELOW_SURVEY_TOLERANCE_M:
                    continue
                below = log.data[curve.mnemonic].dropna()
                n_below = int((below.index.to_numpy() * scale > limit.value).sum())
                curve_fact = Fact(
                    name=f"{curve.mnemonic}_base_md_m",
                    value=round(base, 4),
                    unit="m",
                    provenance=[
                        Provenance(
                            source_file=relative(log.path),
                            locator=f"LAS:~Curve/{curve.mnemonic} last non-null sample",
                            method="parsed",
                        )
                    ],
                )
                what = "final survey station" if limit.name == "final_survey_md_m" else "TD"
                flags.append(
                    ReviewFlag(
                        severity="warn",
                        fact=curve_fact.name,
                        reason="log_below_survey" if what != "TD" else "log_below_td",
                        message=(
                            f"{log.path.name} curve {curve.mnemonic} has data down to "
                            f"{base:.1f} m MD, {base - limit.value:.1f} m below the {what} at "
                            f"{limit.value:.1f} m MD ({n_below:,} non-null samples deeper)"
                        ),
                        candidates=[curve_fact, limit],
                    )
                )
    return issues, flags


def rule5_units(records: list[Record], namespace: str) -> list[Issue]:
    """Depths are in metres; curves without a mapped unit are reported (abstained, not guessed)."""
    metre = f"{namespace}:reference-data--UnitOfMeasure:m:"
    issues = []
    for rec in records:
        if rec.type != "WellLog":
            continue
        for i, curve in enumerate(rec.data.get("Curves", [])):
            if curve.get("DepthUnit") != metre:
                issues.append(
                    Issue(
                        rule=5,
                        severity="error",
                        record_id=rec.id,
                        path=f"Curves[{i}].DepthUnit",
                        message="curve depth unit is not metres",
                    )
                )
            if "CurveUnit" not in curve:
                issues.append(
                    Issue(
                        rule=5,
                        severity="info",
                        record_id=rec.id,
                        path=f"Curves[{i}].CurveUnit",
                        message=f"{curve['Mnemonic']}: unit not mapped, left empty",
                    )
                )
    return issues


def rule6_geography(facts: dict[str, Fact]) -> list[ReviewFlag]:
    """Surface location must be inside the Volve box, else block (swapped axes or wrong CRS)."""
    lat, lon = facts.get("surface_latitude_deg"), facts.get("surface_longitude_deg")
    if not lat or not lon or lat.value is None or lon.value is None:
        return []
    assert isinstance(lat.value, float) and isinstance(lon.value, float)
    (lat_min, lat_max), (lon_min, lon_max) = VOLVE_BOX["lat"], VOLVE_BOX["lon"]
    if lat_min <= lat.value <= lat_max and lon_min <= lon.value <= lon_max:
        return []
    return [
        ReviewFlag(
            severity="block",
            fact="surface_location",
            reason="outside_volve",
            message=f"surface location ({lat.value}, {lon.value}) is outside the Volve area",
            candidates=[lat, lon],
        )
    ]


def rule7_provenance(records: list[Record]) -> list[Issue]:
    """Every populated data field has at least one provenance entry (own path or a parent's)."""
    issues = []
    for rec in records:
        keys = [k for k, sources in rec.provenance.items() if sources]
        for path, _value in walk(rec.to_json()["data"]):
            if not any(path == k or path.startswith((k + ".", k + "[")) for k in keys):
                issues.append(
                    Issue(
                        rule=7,
                        severity="error",
                        record_id=rec.id,
                        path=path,
                        message="value has no provenance",
                    )
                )
    return issues


def rule10_plans(wellpath: WellPath | None) -> list[ReviewFlag]:
    """A plan or prototype well path is never the definitive (actual) trajectory."""
    if wellpath is None or not wellpath.is_plan:
        return []
    return [
        ReviewFlag(
            severity="block",
            fact="trajectory",
            reason="plan_not_actual",
            message=f"{wellpath.path.name} is a plan/prototype, not the drilled well path; "
            "no trajectory record was created",
        )
    ]


def _depth_issue(rec: Record, path: str, message: str) -> Issue:
    return Issue(rule=4, severity="error", record_id=rec.id, path=path, message=message)
