"""Shared fixtures: small, in-memory OSDU records built from the fixture files."""

from pathlib import Path

import pytest

from volve_osdu.extract.curves import map_curve
from volve_osdu.facts import Fact, Provenance
from volve_osdu.ingest.las import LasLog, read_las
from volve_osdu.ingest.wellpath import WellPath, read_wellpath
from volve_osdu.osdu.records import Builder, Record

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "data" / "raw" / "osdu-python-models" / "schemas" / "M27.1"
needs_schemas = pytest.mark.skipif(not SCHEMAS.exists(), reason="schemas not downloaded")


def parsed(name: str, value: float | str) -> Fact:
    return Fact(
        name=name,
        value=value,
        provenance=[
            Provenance(source_file="sample.las", locator=f"LAS:~Well/{name}", method="parsed")
        ],
    )


@pytest.fixture
def las() -> LasLog:
    return read_las(FIXTURES / "sample.las")


@pytest.fixture
def wellpath() -> WellPath:
    return read_wellpath(FIXTURES / "sample_wellpath.txt")


@pytest.fixture
def records(las: LasLog, wellpath: WellPath) -> list[Record]:
    """Organisation, Field, Well, Wellbore, trajectory, a WellLog and their datasets."""
    b = Builder("volve", '{"authCode":{"auth":"EPSG","code":"4230"}}')
    facts = {
        "kb_elevation_m": parsed("kb_elevation_m", 54.9),
        "surface_latitude_deg": parsed("surface_latitude_deg", 58.441713),
        "surface_longitude_deg": parsed("surface_longitude_deg", 1.88748),
        "td_md_m": parsed("td_md_m", 3520.0),
    }
    org = b.organisation(parsed("operator_name", "STATOILHYDRO"))
    field = b.field(parsed("field_name", "VOLVE"))
    well = b.well(parsed("well_name", "15/9-F-12"), facts, org, field)
    stub = Record("Wellbore", "volve:master-data--Wellbore:NO-15-9-F-12", {})
    traj_ds = b.dataset("NO-15-9-F-12-trajectory", "bulk/t.parquet", 10, "0" * 32, "t.parquet")
    traj = b.trajectory(wellpath, stub, facts["kb_elevation_m"], traj_ds)
    wellbore = b.wellbore(parsed("wellbore_name", "15/9-F-12"), [], well, facts, org, field, traj)
    log_ds = b.dataset("NO-15-9-F-12-log", "bulk/l.parquet", 10, "0" * 32, "l.parquet")
    mappings = [map_curve(c.mnemonic, c.unit) for c in las.curves]
    log = b.well_log(las, wellbore, mappings, log_ds, 1.0)
    return [org, field, well, wellbore, traj_ds, traj, log_ds, log]
