"""Tests for the record builders: IDs, references, vertical measurements, schema validity."""

from conftest import needs_schemas
from volve_osdu.osdu.manifest import build_manifest
from volve_osdu.osdu.records import Record
from volve_osdu.validate.schema import validate_manifest, validate_record


def by_type(records: list[Record], type_: str) -> Record:
    return next(r for r in records if r.type == type_)


def test_wellbore_links_and_measurements(records: list[Record]) -> None:
    wb = by_type(records, "Wellbore").to_json()["data"]
    assert wb["WellID"] == "volve:master-data--Well:NO-15-9-F-12:"
    vms = {vm["VerticalMeasurementID"]: vm for vm in wb["VerticalMeasurements"]}
    assert vms["KB"]["VerticalMeasurement"] == 54.9
    assert vms["TD"]["VerticalMeasurementPathID"].endswith("VerticalMeasurementPath:MeasuredDepth:")
    assert vms["TD"]["VerticalReferenceID"] == "KB"
    assert wb["DefinitiveTrajectoryID"].startswith(
        "volve:work-product-component--WellboreTrajectory:"
    )


def test_well_location_is_lon_lat_in_ed50(records: list[Record]) -> None:
    loc = by_type(records, "Well").to_json()["data"]["SpatialLocation"]["AsIngestedCoordinates"]
    assert loc["CoordinateReferenceSystemID"].endswith("Geographic2D:EPSG::4230:")
    assert loc["features"][0]["geometry"]["coordinates"] == [1.88748, 58.441713]  # GeoJSON order


def test_well_log_curves_have_valid_ranges_and_mappings(records: list[Record]) -> None:
    log = by_type(records, "WellLog").to_json()["data"]
    gr = log["Curves"][0]
    assert gr["Mnemonic"] == "GR"
    assert gr["CurveUnit"] == "volve:reference-data--UnitOfMeasure:gAPI:"
    assert gr["LogCurveFamilyID"] == "volve:reference-data--LogCurveFamily:Gamma%20Ray:"
    assert log["Curves"][1]["BaseDepth"] == 3500.1524  # RHOB is null below this
    assert log["NullValue"] == "-999.25"


@needs_schemas
def test_every_record_and_the_manifest_pass_the_pinned_schemas(records: list[Record]) -> None:
    for rec in records:
        assert validate_record(rec.to_json()) == [], rec.id
    assert validate_manifest(build_manifest(records)) == []


@needs_schemas
def test_schema_catches_a_reference_without_version_separator(records: list[Record]) -> None:
    doc = by_type(records, "Wellbore").to_json()
    doc["data"]["WellID"] = "volve:master-data--Well:NO-15-9-F-12"
    issues = validate_record(doc)
    assert [i.path for i in issues] == ["data.WellID"]
