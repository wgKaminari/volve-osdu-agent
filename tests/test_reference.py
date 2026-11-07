"""Tests for the reference-value loader (fixture) and our IDs against the real pinned lists."""

import json
from pathlib import Path

import pytest

from volve_osdu.osdu.ids import reference_data_id
from volve_osdu.osdu.reference import load_reference_ids

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "raw" / "reference"


def test_load_reference_ids_fills_namespace(tmp_path: Path) -> None:
    path = tmp_path / "VerticalMeasurementType.1.json"
    manifest = {
        "ReferenceData": [
            {"id": "{{NAMESPACE}}:reference-data--VerticalMeasurementType:KellyBushing"},
            {"id": "{{NAMESPACE}}:reference-data--VerticalMeasurementType:TotalDepth"},
        ]
    }
    path.write_text(json.dumps(manifest))
    ids = load_reference_ids(path, "volve")
    assert "volve:reference-data--VerticalMeasurementType:KellyBushing:" in ids
    assert len(ids) == 2


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference data not downloaded")
@pytest.mark.parametrize(
    ("file", "ref_type", "code"),
    [
        ("VerticalMeasurementType.1.json", "VerticalMeasurementType", "KellyBushing"),
        ("VerticalMeasurementType.1.json", "VerticalMeasurementType", "TotalDepth"),
        ("VerticalMeasurementType.1.json", "VerticalMeasurementType", "KickOffPoint"),
        ("VerticalMeasurementPath.1.json", "VerticalMeasurementPath", "MeasuredDepth"),
        ("VerticalMeasurementPath.1.json", "VerticalMeasurementPath", "ELEV"),
        ("UnitOfMeasure.1.json", "UnitOfMeasure", "m"),
        ("UnitOfMeasure.1.json", "UnitOfMeasure", "gAPI"),
        ("LogCurveFamily.1.json", "LogCurveFamily", "Gamma Ray"),
        (
            "CoordinateReferenceSystem.1.json",
            "CoordinateReferenceSystem",
            "Geographic2D:EPSG::4230",
        ),
    ],
)
def test_ids_we_use_exist_in_pinned_reference_lists(file: str, ref_type: str, code: str) -> None:
    ids = load_reference_ids(REFERENCE / file, "volve")
    if ref_type == "CoordinateReferenceSystem":
        # CRS codes contain ':' that the reference list keeps unencoded.
        ref = f"volve:reference-data--{ref_type}:{code}:"
    else:
        ref = reference_data_id("volve", ref_type, code)
    assert ref in ids
