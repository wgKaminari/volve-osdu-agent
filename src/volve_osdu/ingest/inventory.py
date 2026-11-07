"""File inventory for one wellbore bundle (pipeline step 1, deterministic)."""

from dataclasses import dataclass, field
from pathlib import Path

from volve_osdu.config import Bundle
from volve_osdu.ingest.las import LasLog, read_las
from volve_osdu.ingest.pdf import PdfDocument, read_pdf
from volve_osdu.ingest.wellpath import WellPath, is_plan, read_wellpath


@dataclass
class Inventory:
    logs: list[LasLog]
    pdf: PdfDocument | None
    wellpath: WellPath | None
    missing: list[Path] = field(default_factory=list)


def take_inventory(bundle: Bundle) -> Inventory:
    """Read every input file that exists. Missing files are listed, never silently skipped."""
    missing = [p for p in [*bundle.las, bundle.pdf, bundle.wellpath] if p and not p.is_file()]
    logs = [read_las(p) for p in bundle.las if p.is_file()]
    pdf = read_pdf(bundle.pdf) if bundle.pdf and bundle.pdf.is_file() else None
    wellpath = (
        read_wellpath(bundle.wellpath) if bundle.wellpath and bundle.wellpath.is_file() else None
    )
    return Inventory(logs=logs, pdf=pdf, wellpath=wellpath, missing=missing)


def scan_wellpaths(folder: Path) -> tuple[list[Path], list[Path]]:
    """Split a well path folder into (actual, plan/prototype) files. Plans are never used."""
    files = sorted(p for p in folder.iterdir() if p.is_file())
    return [p for p in files if not is_plan(p)], [p for p in files if is_plan(p)]
