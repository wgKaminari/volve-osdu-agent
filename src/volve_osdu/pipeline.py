"""One wellbore end to end: inventory -> facts -> reconcile -> records -> validate -> outputs.

The "system" (rules, llm_only or agent) only decides the judgement steps: which wellbore this is,
facts from report prose, and curve mappings. Everything numeric and every check is shared code,
so the systems are compared on exactly the judgement they add.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from volve_osdu.config import RAW, REFERENCE_DIR, Bundle, relative
from volve_osdu.extract.curves import CurveMapping, map_curve
from volve_osdu.extract.names import well_name_of
from volve_osdu.extract.parsed import FEET_TO_M, las_facts
from volve_osdu.extract.pdf_rules import pdf_rule_facts
from volve_osdu.facts import Fact, Issue, Provenance, ReviewFlag
from volve_osdu.ingest.inventory import Inventory, scan_wellpaths, take_inventory
from volve_osdu.osdu.bulk import write_parquet
from volve_osdu.osdu.ids import wellbore_code
from volve_osdu.osdu.manifest import build_manifest
from volve_osdu.osdu.records import CRS_CODE, Builder, Record
from volve_osdu.osdu.reference import load_reference_data
from volve_osdu.reconcile import reconcile
from volve_osdu.report import write_review
from volve_osdu.validate import rules
from volve_osdu.validate.grounding import check_grounding
from volve_osdu.validate.schema import validate_manifest, validate_record

logger = logging.getLogger(__name__)
WELLPATH_FOLDER = RAW / "volve_field_data" / "input_data" / "wellpaths"


@dataclass
class Judgement:
    """What a system decides for one wellbore. Numbers in `facts` must carry provenance."""

    wellbore_name: Fact | None
    aliases: list[tuple[str, Provenance]]
    facts: list[Fact]
    mappings: dict[str, list[CurveMapping]]  # LAS file name -> curve mappings
    flags: list[ReviewFlag] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)  # one entry per LLM call
    stats: dict[str, Any] = field(default_factory=dict)  # system-specific counters (stats.json)


System = Callable[[Inventory, list[Fact]], Judgement]


def rules_system(inv: Inventory, parsed: list[Fact]) -> Judgement:
    """Baseline without LLM: most specific LAS name, regex on PDF prose, static curve dictionary."""
    names = [f for f in parsed if f.name == "wellbore_name"]
    aliases = [(p.quote or str(f.value), p) for f in names for p in f.provenance]
    chosen = None
    if names:
        best = max(names, key=lambda f: len(str(f.value)))
        sources = [p for f in names if f.value == best.value for p in f.provenance]
        chosen = Fact(name="wellbore_name", value=best.value, provenance=sources)
    flags = []
    if chosen is not None:
        others = {
            str(f.value)
            for f in names
            if f.value != chosen.value and not str(chosen.value).startswith(str(f.value))
        }
        if others:
            flags.append(
                ReviewFlag(
                    severity="warn",
                    fact="wellbore_name",
                    reason="conflict",
                    message=f"files name different wellbores: {chosen.value} vs {sorted(others)}",
                    candidates=names,
                )
            )
    facts = pdf_rule_facts(inv.pdf, str(chosen.value)) if inv.pdf and chosen else []
    mappings = {
        log.path.name: [map_curve(c.mnemonic, c.unit) for c in log.curves] for log in inv.logs
    }
    return Judgement(chosen, aliases, facts, mappings, flags)


SYSTEMS: dict[str, System] = {"rules": rules_system}


@dataclass
class RunResult:
    wellbore: str
    out_dir: Path
    records: int
    flags: list[ReviewFlag]
    issues: list[Issue]

    @property
    def valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def run_wellbore(bundle: Bundle, system: str | System, out_root: Path, namespace: str) -> RunResult:
    system_fn = SYSTEMS[system] if isinstance(system, str) else system
    system = system if isinstance(system, str) else getattr(system, "name", "custom")
    out_dir = out_root / bundle.folder.name
    inv = take_inventory(bundle)
    flags: list[ReviewFlag] = []
    issues: list[Issue] = [
        Issue(rule=0, severity="warn", record_id=None, message=f"input file missing: {relative(p)}")
        for p in inv.missing
    ]

    parsed: list[Fact] = []
    depth_scales: dict[str, float] = {}
    for log in inv.logs:
        facts, las_flags = las_facts(log)
        parsed += facts
        flags += las_flags
        scale = _depth_scale(log.depth_unit)
        if scale is None:
            issues.append(
                Issue(
                    rule=5,
                    severity="error",
                    record_id=None,
                    path=log.path.name,
                    message=f"unknown depth unit {log.depth_unit!r}; file skipped",
                )
            )
            continue
        if scale != 1.0:
            flags.append(
                ReviewFlag(
                    severity="info",
                    fact="depth",
                    reason="unit_converted",
                    message=f"{log.path.name}: depths converted from ft to m",
                )
            )
        depth_scales[log.path.name] = scale

    judgement = system_fn(inv, parsed)
    flags += judgement.flags
    issues += judgement.issues
    trace = judgement.trace
    _write_json(out_dir / "stats.json", judgement.stats)
    # Rule 8 again, independent of the system: validators judge, whatever produced the fact.
    judgement.facts, grounding_flags = _grounded(judgement.facts, inv)
    flags += grounding_flags
    if judgement.wellbore_name is None or judgement.wellbore_name.value is None:
        issues.append(
            Issue(
                rule=0,
                severity="error",
                record_id=None,
                message="could not determine the wellbore name; nothing built",
            )
        )
        return _finish(bundle, out_dir, [], {}, flags, issues, inv, system, trace)

    header_facts = [f for f in parsed if f.name != "wellbore_name"]
    resolved, conflict_flags = reconcile(header_facts + judgement.facts)
    flags += conflict_flags

    name = judgement.wellbore_name
    well_name = Fact(
        name="well_name",
        value=well_name_of(str(name.value)),
        provenance=[
            *name.provenance,
            Provenance(
                source_file="(pipeline)", locator="rule: sidetrack suffix removed", method="derived"
            ),
        ],
    )
    crs = load_reference_data(REFERENCE_DIR / "CoordinateReferenceSystem.1.json", namespace)
    crs_ref = crs.get(f"{namespace}:reference-data--CoordinateReferenceSystem:{CRS_CODE}:", {})
    builder = Builder(namespace, crs_ref.get("PersistableReference"))
    code = wellbore_code(str(name.value))

    operator = (
        builder.organisation(resolved["operator_name"]) if _has(resolved, "operator_name") else None
    )
    field_rec = builder.field(resolved["field_name"]) if _has(resolved, "field_name") else None
    well = builder.well(well_name, resolved, operator, field_rec)
    if "SpatialLocation" in well.data:
        # LAS headers state no datum. Volve LAS files are known to mix ED50 and WGS84
        # (docs/architecture.md), so the CRS we record is an assumption a human must confirm.
        flags.append(
            ReviewFlag(
                severity="warn",
                fact="surface_location",
                reason="crs_assumed",
                message="LAS LAT/LON state no datum; recorded as ED50 (EPSG:4230). Confirm the "
                "datum before ingestion (an ED50/WGS84 mix-up moves the well ~100 m).",
                candidates=[resolved["surface_latitude_deg"], resolved["surface_longitude_deg"]],
            )
        )

    records: list[Record] = [r for r in (operator, field_rec, well) if r is not None]
    bulk_dir = out_dir / "bulk"
    trajectory = None
    wellbore_stub = Record("Wellbore", f"{namespace}:master-data--Wellbore:{code}", {})
    if inv.wellpath is not None and not inv.wellpath.is_plan:
        file = f"{code}-trajectory.parquet"
        size, md5 = write_parquet(inv.wellpath.stations, bulk_dir / file)
        dataset = builder.dataset(f"{code}-trajectory", f"bulk/{file}", size, md5, file)
        trajectory = builder.trajectory(
            inv.wellpath, wellbore_stub, resolved.get("kb_elevation_m"), dataset
        )
        records += [dataset, trajectory]
    flags += rules.rule10_plans(inv.wellpath)

    wellbore = builder.wellbore(
        name, _aliases(judgement, bundle), well, resolved, operator, field_rec, trajectory
    )
    records.append(wellbore)

    logs_used = []
    for log in inv.logs:
        scale = depth_scales.get(log.path.name)
        if scale is None:
            continue
        file = f"{code}-{log.path.stem}.parquet"
        frame = log.data.copy().reset_index()  # copy() defragments wide LAS frames
        frame[frame.columns[0]] = frame[frame.columns[0]] * scale
        size, md5 = write_parquet(frame, bulk_dir / file)
        dataset = builder.dataset(f"{code}-{log.path.stem}", f"bulk/{file}", size, md5, file)
        records += [
            dataset,
            builder.well_log(
                log, wellbore, judgement.mappings.get(log.path.name, []), dataset, scale
            ),
        ]
        logs_used.append((log, scale))

    issues += _schema_and_model_issues(records)
    issues += rules.rule2_references(records)
    issues += rules.rule3_reference_values(records, namespace)
    depth_issues, depth_flags = rules.rule4_depths(records, logs_used, inv.wellpath, resolved)
    issues += depth_issues
    flags += depth_flags
    issues += rules.rule5_units(records, namespace)
    flags += rules.rule6_geography(resolved)
    issues += rules.rule7_provenance(records)
    return _finish(bundle, out_dir, records, resolved, flags, issues, inv, system, trace)


def _finish(
    bundle: Bundle,
    out_dir: Path,
    records: list[Record],
    facts: dict[str, Fact],
    flags: list[ReviewFlag],
    issues: list[Issue],
    inv: Inventory,
    system: str,
    trace: list[dict[str, Any]],
) -> RunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    if trace:
        lines = [json.dumps({"wellbore": bundle.canonical_name, **t}) for t in trace]
        (out_dir / "trace.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Records whose data block fails the Pydantic model can't be serialized; leave them out.
    broken = {i.record_id for i in issues if i.rule == 1 and i.message.startswith("pydantic")}
    records = [r for r in records if r.id not in broken]
    if records:
        manifest = build_manifest(records)
        issues += validate_manifest(manifest)
        _write_json(out_dir / "manifest.json", manifest)
        for rec in records:
            _write_json(
                out_dir / "records" / f"{rec.id.rsplit(':', 1)[1]}.{rec.type}.json", rec.to_json()
            )
    _write_json(
        out_dir / "provenance.json",
        {
            rec.id: {
                path: [p.model_dump(exclude_none=True) for p in sources]
                for path, sources in rec.provenance.items()
            }
            for rec in records
        },
    )
    _write_json(
        out_dir / "facts.json",
        {
            name: fact.model_dump(exclude_none=True) | {"value": fact.value}
            for name, fact in facts.items()
        },
    )
    _write_json(
        out_dir / "validation.json",
        {
            "issues": [i.model_dump() for i in issues],
            "flags": [f.model_dump(exclude_none=True) for f in flags],
        },
    )
    _, plans = scan_wellpaths(WELLPATH_FOLDER) if WELLPATH_FOLDER.exists() else ([], [])
    write_review(
        out_dir / "review.md",
        bundle=bundle,
        system=system,
        records=records,
        facts=facts,
        flags=flags,
        issues=issues,
        inv=inv,
        excluded_plans=plans,
    )
    result = RunResult(bundle.canonical_name, out_dir, len(records), flags, issues)
    logger.info(
        "%s: %d records, %d flags, %d errors -> %s",
        bundle.canonical_name,
        len(records),
        len(flags),
        sum(i.severity == "error" for i in issues),
        relative(out_dir),
    )
    return result


def _schema_and_model_issues(records: list[Record]) -> list[Issue]:
    issues = []
    for rec in records:
        try:
            doc = rec.to_json()
        except ValueError as exc:  # pydantic.ValidationError is a ValueError
            issues.append(
                Issue(
                    rule=1,
                    severity="error",
                    record_id=rec.id,
                    message=f"pydantic: {str(exc)[:300]}",
                )
            )
            continue
        issues += validate_record(doc)
    return issues


def _grounded(facts: list[Fact], inv: Inventory) -> tuple[list[Fact], list[ReviewFlag]]:
    """Keep llm_extracted PDF facts only if their quote and value check out (rule 8)."""
    kept, flags = [], []
    for fact in facts:
        prov = fact.provenance[0] if fact.provenance else None
        if prov is None or prov.method != "llm_extracted" or not prov.locator.startswith("PDF:"):
            kept.append(fact)
            continue
        checked, reason = check_grounding(fact, inv.pdf) if inv.pdf else (None, "no report")
        if checked is None and fact.name == "kickoff_wellbore_name" and inv.pdf:
            # The value was normalized ("F-1" -> "15/9-F-1"); the quote must still be in the text.
            short = str(fact.value).split("-", 1)[-1]  # "15/9-F-1" -> "F-1"
            quote = prov.quote or ""
            checked = fact if inv.pdf.find_quote(quote) and short in quote else None
        if checked is None:
            flags.append(
                ReviewFlag(
                    severity="warn",
                    fact=fact.name,
                    reason="ungrounded",
                    message=f"dropped {fact.value!r}: {reason}",
                    candidates=[fact],
                )
            )
        else:
            kept.append(checked)
    return kept, flags


def _aliases(judgement: Judgement, bundle: Bundle) -> list[tuple[str, Provenance]]:
    folder = Provenance(source_file=relative(bundle.folder), locator="folder name", method="parsed")
    return [*judgement.aliases, (bundle.folder.name, folder)]


def _depth_scale(unit: str) -> float | None:
    unit = unit.strip().upper()
    if unit in ("M", "METERS", "METRES"):
        return 1.0
    if unit in ("F", "FT", "FEET"):
        return FEET_TO_M
    return None


def _has(facts: dict[str, Fact], name: str) -> bool:
    return name in facts and facts[name].value is not None


def _write_json(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
