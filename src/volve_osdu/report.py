"""review.md: the human-readable summary of one wellbore run (pipeline step 8)."""

from pathlib import Path

from volve_osdu.config import Bundle, relative
from volve_osdu.facts import Fact, Issue, ReviewFlag
from volve_osdu.ingest.inventory import Inventory
from volve_osdu.osdu.records import Record

SEVERITY_ORDER = {"block": 0, "error": 0, "warn": 1, "info": 2}


def write_review(
    path: Path,
    *,
    bundle: Bundle,
    system: str,
    records: list[Record],
    facts: dict[str, Fact],
    flags: list[ReviewFlag],
    issues: list[Issue],
    inv: Inventory,
    excluded_plans: list[Path],
) -> None:
    errors = [i for i in issues if i.severity == "error"]
    lines = [
        f"# Review: {bundle.canonical_name}",
        "",
        f"System: `{system}` · Records: {len(records)} · Review flags: {len(flags)} · "
        f"Validation errors: {len(errors)}",
        "",
        "**Status: "
        + ("ready to ingest after review" if not errors else "NOT valid, see errors")
        + "**",
        "",
        "## Review flags",
        "",
    ]
    if flags:
        lines += ["| Severity | Fact | Reason | Details | Sources |", "|---|---|---|---|---|"]
        for flag in sorted(flags, key=lambda f: SEVERITY_ORDER[f.severity]):
            sources = "; ".join(
                f"{c.value} ← {p.source_file} ({p.locator})"
                for c in flag.candidates
                for p in c.provenance
            )
            lines.append(
                f"| {flag.severity} | {flag.fact} | {flag.reason} | {_cell(flag.message)} "
                f"| {_cell(sources) or '-'} |"
            )
    else:
        lines.append("None.")

    lines += ["", "## Facts used", "", "| Fact | Value | Sources |", "|---|---|---|"]
    for name, fact in sorted(facts.items()):
        sources = "; ".join(
            f"{p.source_file} ({p.locator})" + (f' "{p.quote}"' if p.quote else "")
            for p in fact.provenance
        )
        value = "(abstained)" if fact.value is None else f"{fact.value} {fact.unit or ''}".strip()
        lines.append(f"| {name} | {value} | {_cell(sources)} |")

    lines += ["", "## Records", ""]
    lines += [f"- `{r.kind}` `{r.id}`" for r in records] or ["None."]

    lines += ["", "## Inputs", ""]
    lines += [f"- LAS: `{relative(log.path)}`" for log in inv.logs]
    if inv.pdf:
        heavy = " (image-heavy: few facts can be read as text)" if inv.pdf.is_image_heavy else ""
        lines.append(f"- PDF: `{relative(inv.pdf.path)}`, {len(inv.pdf.pages)} pages{heavy}")
    if inv.wellpath:
        kind = "PLAN, not used" if inv.wellpath.is_plan else "actual"
        lines.append(f"- Well path: `{relative(inv.wellpath.path)}` ({kind})")
    lines += [f"- Missing: `{relative(p)}`" for p in inv.missing]
    if excluded_plans:
        names = ", ".join(f"`{p.name}`" for p in excluded_plans)
        lines.append(f"- Plan/prototype well paths in the folder, never used: {names}")

    lines += ["", "## Validation", ""]
    shown = [i for i in issues if i.severity != "info"]
    infos = len(issues) - len(shown)
    if shown:
        lines += ["| Rule | Severity | Record | Path | Message |", "|---|---|---|---|---|"]
        for i in sorted(shown, key=lambda i: (SEVERITY_ORDER[i.severity], i.rule)):
            lines.append(
                f"| {i.rule} | {i.severity} | {i.record_id or '-'} | {i.path or '-'} "
                f"| {_cell(i.message)} |"
            )
    else:
        lines.append("All checks passed (rules 1-7, 9, 10).")
    if infos:
        lines += ["", f"{infos} info notes (e.g. curves left unmapped) are in validation.json."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
