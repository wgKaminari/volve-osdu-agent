"""Assemble records into an OSDU load manifest (osdu:wks:Manifest:1.0.0).

Load order matters to OSDU: master data first (Organisation, Field, Well, then Wellbore), then
Datasets, then the work-product components that point to them.
"""

from typing import Any

from volve_osdu.osdu.records import Record

MANIFEST_KIND = "osdu:wks:Manifest:1.0.0"
MASTER_ORDER = ["Organisation", "Field", "Well", "Wellbore"]


def build_manifest(records: list[Record]) -> dict[str, Any]:
    master = sorted(
        (r for r in records if r.type in MASTER_ORDER), key=lambda r: MASTER_ORDER.index(r.type)
    )
    datasets = [r for r in records if r.type == "File.Generic"]
    wpcs = [r for r in records if r.type in ("WellLog", "WellboreTrajectory")]
    return {
        "kind": MANIFEST_KIND,
        "MasterData": [r.to_json() for r in master],
        "Data": {
            "WorkProductComponents": [r.to_json() for r in wpcs],
            "Datasets": [r.to_json() for r in datasets],
        },
    }
