"""Injected conflicts: copies of real bundles with one controlled change each (guide 8.2).

Each perturbation states the review flag it should trigger (or none, for negative controls). The
copies live in .cache/perturbed/<id>/ (gitignored) and run through the same systems as the real
bundles, so review-flag precision/recall is measured on known answers.
"""

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from volve_osdu.config import ROOT, Bundle, find_bundle

PERTURBED = ROOT / ".cache" / "perturbed"
FT_PER_M = 3.280839895


@dataclass(frozen=True)
class Perturbation:
    id: str
    wellbore: str  # canonical name of the source bundle
    description: str
    expected_fact: str | None  # flag we expect; "*" = any curve; None = negative control
    expected_reason: str | None
    apply: Callable[[Path], None]  # edits the copied bundle folder in place


# --- LAS text edits (LAS 2.0 lines: "MNEM.UNIT  VALUE : DESCRIPTION") -------------------------


def set_header(text: str, mnemonic: str, value: str, unit: str | None = None) -> str:
    """Replace a ~Well item's value (and unit), or insert the item before ~Curve if missing."""
    lines = text.splitlines()
    pattern = re.compile(rf"^\s*{re.escape(mnemonic)}\s*\.")
    for i, line in enumerate(lines):
        if pattern.match(line):
            dot = line.index(".")
            old_unit = re.match(r"\S*", line[dot + 1 :]).group(0)  # type: ignore[union-attr]
            colon = line.rindex(":")
            new_unit = unit if unit is not None else old_unit
            lines[i] = f"{line[:dot]}.{new_unit:<8} {value:>30} {line[colon:]}"
            return "\n".join(lines) + "\n"
    for i, line in enumerate(lines):
        if line.upper().startswith("~C"):
            lines.insert(i, f"{mnemonic:<11} .{unit or '':<8} {value:>30} :ADDED BY PERTURBATION")
            return "\n".join(lines) + "\n"
    raise ValueError("no ~Curve section")


def delete_header(text: str, mnemonic: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(mnemonic)}\s*\.")
    return "\n".join(line for line in text.splitlines() if not pattern.match(line)) + "\n"


def depth_to_feet(text: str) -> str:
    """Convert STRT/STOP/STEP, the depth curve unit and the first data column from m to ft."""
    out, section, depth_unit_done = [], "", False
    for line in text.splitlines():
        if line.startswith("~"):
            section = line[1].upper()
            out.append(line)
            continue
        stripped = line.strip()
        if section == "W" and re.match(r"^(STRT|STOP|STEP)\s*\.M\b", stripped):
            mnem = stripped.split(".")[0].strip()
            value = float(stripped.split(".M", 1)[1].split(":")[0])
            line = f"{mnem:<11} .F {value * FT_PER_M:>20.4f} :{line.rsplit(':', 1)[1]}"
        elif section == "C" and not depth_unit_done and stripped and not stripped.startswith("#"):
            line = re.sub(r"\.M\b", ".F", line, count=1)
            depth_unit_done = True
        elif section == "A" and stripped and not stripped.startswith("#"):
            first, *rest = stripped.split()
            line = " ".join([f"{float(first) * FT_PER_M:.4f}", *rest])
        out.append(line)
    return "\n".join(out) + "\n"


def edit_las(name: str, edit: Callable[[str], str]) -> Callable[[Path], None]:
    def apply(folder: Path) -> None:
        path = folder / name
        path.write_text(edit(path.read_text(encoding="latin-1")), encoding="latin-1")

    return apply


def edit_all_las(edit: Callable[[str], str]) -> Callable[[Path], None]:
    def apply(folder: Path) -> None:
        for path in folder.glob("*.[lL][aA][sS]"):
            path.write_text(edit(path.read_text(encoding="latin-1")), encoding="latin-1")

    return apply


def rename_las_files(folder: Path) -> None:
    for i, path in enumerate(sorted(folder.glob("*.[lL][aA][sS]"))):
        path.rename(path.with_name(f"log_{i}.las"))


def rename_wellpath(new_name: str) -> Callable[[Path], None]:
    def apply(folder: Path) -> None:
        (folder / "wellpath").rename(folder / "wellpath-renamed")
        (folder / "wellpath-renamed").rename(folder / new_name)

    return apply


def truncate_wellpath(max_md: float) -> Callable[[Path], None]:
    def apply(folder: Path) -> None:
        path = folder / "wellpath"
        lines = path.read_text(encoding="latin-1").splitlines()
        kept = lines[:2] + [ln for ln in lines[2:] if ln.split() and float(ln.split()[0]) <= max_md]
        path.write_text("\n".join(kept) + "\n", encoding="latin-1")

    return apply


IN, OUT = "WLC_PETRO_COMPUTED_INPUT_1.LAS", "WLC_PETRO_COMPUTED_OUTPUT_1.LAS"

PERTURBATIONS = [
    Perturbation(
        "P01",
        "15/9-F-12",
        "INPUT LAS depths converted to feet",
        "depth",
        "unit_converted",
        edit_las(IN, depth_to_feet),
    ),
    Perturbation(
        "P02",
        "15/9-F-12",
        "LAT and LON swapped in both LAS files",
        "surface_location",
        "outside_volve",
        edit_all_las(lambda t: set_header(set_header(t, "LAT", "1.887480"), "LON", "58.441713")),
    ),
    Perturbation(
        "P03",
        "15/9-F-12",
        "KB elevation 54.9 -> 59.9 m in the OUTPUT LAS only",
        "kb_elevation_m",
        "conflict",
        edit_las(OUT, lambda t: set_header(t, "ELEV", "59.9000")),
    ),
    Perturbation(
        "P04",
        "15/9-F-1 A",
        "actual well path renamed to a PLAN",
        "trajectory",
        "plan_not_actual",
        rename_wellpath("F-1 A Rev3 PLAN"),
    ),
    Perturbation(
        "P05",
        "15/9-F-1 A",
        "well path truncated at 3000 m MD",
        "*",
        "log_below_survey",
        truncate_wellpath(3000.0),
    ),
    Perturbation(
        "P06",
        "15/9-F-11 A",
        "field name SLEIPNER in the OUTPUT LAS",
        "field_name",
        "conflict",
        edit_las(OUT, lambda t: set_header(t, "FLD", "SLEIPNER")),
    ),
    Perturbation(
        "P07",
        "15/9-F-11 B",
        "OUTPUT LAS names wellbore 15/9-F-11 A",
        "wellbore_name",
        "conflict",
        edit_las(OUT, lambda t: set_header(t, "WELL", "15/9-F-11 A")),
    ),
    Perturbation(
        "P08",
        "15/9-F-15 D",
        "operator Norsk Hydro in the OUTPUT LAS",
        "operator_name",
        "conflict",
        edit_las(OUT, lambda t: set_header(t, "COMP", "Norsk Hydro")),
    ),
    Perturbation(
        "P09",
        "15/9-F-1 C",
        "surface location far outside Volve (60.5 N, 2.5 E)",
        "surface_location",
        "outside_volve",
        edit_all_las(lambda t: set_header(set_header(t, "LAT", "60.500000"), "LON", "2.500000")),
    ),
    Perturbation(
        "P10",
        "15/9-F-1 B",
        "KB 180.1 ft added to the INPUT LAS (= 54.9 m)",
        "kb_elevation_m",
        "unit_converted",
        edit_las(
            IN, lambda t: set_header(set_header(t, "ELEV", "180.1000", "F"), "ELEV_TYPE", "KB")
        ),
    ),
    Perturbation(
        "P11",
        "15/9-F-11 T2",
        "KB 57.0 m added to the INPUT LAS (report says 54.9)",
        "kb_elevation_m",
        "conflict",
        edit_las(
            IN, lambda t: set_header(set_header(t, "ELEV", "57.0000", "M"), "ELEV_TYPE", "KB")
        ),
    ),
    Perturbation(
        "P12",
        "15/9-F-15 D",
        "well path renamed to a PROTOTYPE",
        "trajectory",
        "plan_not_actual",
        rename_wellpath("F-15D rev3 PROTOTYPE"),
    ),
    Perturbation(
        "P13",
        "15/9-F-12",
        "ELEV_TYPE removed (KB can't be confirmed)",
        None,
        None,
        edit_all_las(lambda t: delete_header(t, "ELEV_TYPE")),
    ),
    Perturbation(
        "P14",
        "15/9-F-1",
        "LAS files renamed (names must come from headers)",
        None,
        None,
        rename_las_files,
    ),
]


def build(perturbation: Perturbation) -> Bundle:
    """Copy the source bundle into .cache/perturbed/<id>/ and apply the change."""
    source = find_bundle(perturbation.wellbore)
    folder = PERTURBED / perturbation.id
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for path in source.las:
        shutil.copy2(path, folder / path.name)
    if source.pdf:
        shutil.copy2(source.pdf, folder / source.pdf.name)
    if source.wellpath:
        shutil.copy2(source.wellpath, folder / "wellpath")
    perturbation.apply(folder)
    las = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".las")
    # The well path is the only file that is neither LAS nor PDF (it may have been renamed).
    wellpath = next((p for p in folder.iterdir() if p.suffix.lower() not in (".las", ".pdf")), None)
    return Bundle(
        canonical_name=source.canonical_name,
        folder=folder,
        las=las,
        pdf=folder / source.pdf.name if source.pdf else None,
        wellpath=wellpath,
    )
