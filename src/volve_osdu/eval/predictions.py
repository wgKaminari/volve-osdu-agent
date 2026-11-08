"""Read what a run actually emitted. We score the OSDU records, not intermediate facts, so a value
only counts if it made it into the manifest."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote


@dataclass
class Prediction:
    folder: str
    values: dict[str, float | str | None]  # fact -> emitted value (None = abstained)
    curves: dict[
        str, list[tuple[str, str | None, str | None]]
    ]  # LAS file -> (mnemonic, uom, family)
    flags: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    stats: dict[str, Any]
    facts: dict[str, Any] = field(default_factory=dict)  # facts.json (with provenance)

    @property
    def valid(self) -> bool:
        return not any(i["severity"] == "error" for i in self.issues)


def read_prediction(out_dir: Path) -> Prediction:
    records = [json.loads(p.read_text()) for p in sorted((out_dir / "records").glob("*.json"))]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_type.setdefault(rec["kind"].split(":")[2].split("--")[1], []).append(rec["data"])

    values: dict[str, float | str | None] = {
        k: None
        for k in (
            "wellbore_name",
            "kb_elevation_m",
            "td_md_m",
            "kop_md_m",
            "latitude",
            "longitude",
            "operator",
            "field",
        )
    }
    if wellbores := by_type.get("Wellbore"):
        wb = wellbores[0]
        values["wellbore_name"] = wb.get("FacilityName")
        for vm in wb.get("VerticalMeasurements", []):
            key = {"KB": "kb_elevation_m", "TD": "td_md_m", "KOP": "kop_md_m"}.get(
                vm.get("VerticalMeasurementID", "")
            )
            if key:
                values[key] = vm.get("VerticalMeasurement")
    if wells := by_type.get("Well"):
        loc = wells[0].get("SpatialLocation", {}).get("AsIngestedCoordinates", {})
        features = loc.get("features") or []
        if features:
            lon, lat = features[0]["geometry"]["coordinates"][:2]
            values["latitude"], values["longitude"] = lat, lon
    if orgs := by_type.get("Organisation"):
        values["operator"] = orgs[0].get("OrganisationName")
    if fields_ := by_type.get("Field"):
        values["field"] = fields_[0].get("FieldName")

    curves: dict[str, list[tuple[str, str | None, str | None]]] = {}
    for log in by_type.get("WellLog", []):
        curves[log["Name"]] = [
            (c["Mnemonic"], _code(c.get("CurveUnit")), _code(c.get("LogCurveFamilyID")))
            for c in log.get("Curves", [])
        ]

    validation = _json(out_dir / "validation.json", {"issues": [], "flags": []})
    trace_path = out_dir / "trace.jsonl"
    trace = (
        [json.loads(line) for line in trace_path.read_text().splitlines()]
        if trace_path.exists()
        else []
    )
    return Prediction(
        folder=out_dir.name,
        values=values,
        curves=curves,
        flags=validation["flags"],
        issues=validation["issues"],
        trace=trace,
        stats=_json(out_dir / "stats.json", {}),
        facts=_json(out_dir / "facts.json", {}),
    )


def _code(reference: str | None) -> str | None:
    """ "volve:reference-data--LogCurveFamily:Gamma%20Ray:" -> "Gamma Ray"."""
    if not reference:
        return None
    return unquote(reference.rstrip(":").rsplit(":", 1)[1])


def _json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.exists() else default
