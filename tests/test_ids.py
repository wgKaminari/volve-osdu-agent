"""Tests for OSDU ID builders, checked against the patterns in the pinned M27.1 schemas."""

import re

import pytest

from volve_osdu.osdu.ids import (
    record_id,
    reference,
    reference_data_id,
    wellbore_code,
)

# Patterns copied from schemas/M27.1 (Wellbore.1.5.1 "id", "WellID"; vertical measurement type).
WELLBORE_ID = re.compile(r"^[\w\-\.]+:master-data\-\-Wellbore:[\w\-\.\:\%]+$")
WELL_REF = re.compile(r"^[\w\-\.]+:master-data\-\-Well:[\w\-\.\:\%]+:[0-9]*$")
VM_TYPE_REF = re.compile(
    r"^[\w\-\.]+:reference-data\-\-VerticalMeasurementType:[\w\-\.\:\%]+:[0-9]*$"
)


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("15/9-F-12", "NO-15-9-F-12"),
        ("15/9-F-1 A", "NO-15-9-F-1-A"),
        ("15/9-F-11 T2", "NO-15-9-F-11-T2"),
        ("15/9-19 BT2", "NO-15-9-19-BT2"),
    ],
)
def test_wellbore_code(name: str, code: str) -> None:
    assert wellbore_code(name) == code


def test_record_id_matches_schema_pattern() -> None:
    rid = record_id("volve", "master-data--Wellbore", wellbore_code("15/9-F-1 A"))
    assert rid == "volve:master-data--Wellbore:NO-15-9-F-1-A"
    assert WELLBORE_ID.match(rid)


def test_reference_adds_version_separator() -> None:
    ref = reference(record_id("volve", "master-data--Well", "NO-15-9-F-12"))
    assert ref == "volve:master-data--Well:NO-15-9-F-12:"
    assert WELL_REF.match(ref)


def test_reference_data_id_encodes_like_osdu() -> None:
    assert reference_data_id("volve", "LogCurveFamily", "Gamma Ray") == (
        "volve:reference-data--LogCurveFamily:Gamma%20Ray:"
    )
    vm = reference_data_id("volve", "VerticalMeasurementType", "KellyBushing")
    assert VM_TYPE_REF.match(vm)
