"""Record builders: resolved facts + parsed files -> OSDU records (pipeline step 6).

Pattern from Equinor's osdu-python-models sample (samples/author_welllog.py): the typed model
checks the `data` block, the envelope (id, kind, acl, legal) is a plain dict. Every field we set is
registered in a Provenance map keyed by JSON path, which validation rule 7 checks.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from osdu_models.dataset.file_generic.v1_0_0 import Data as FileGenericData
from osdu_models.masterdata.field.v1_1_0 import Data as FieldData
from osdu_models.masterdata.organisation.v1_2_0 import Data as OrganisationData
from osdu_models.masterdata.well.v1_5_0 import Data as WellData
from osdu_models.masterdata.wellbore.v1_5_1 import Data as WellboreData
from osdu_models.workproductcomponent.well_log.v1_5_0 import Data as WellLogData
from osdu_models.workproductcomponent.wellbore_trajectory.v1_4_0 import Data as TrajectoryData
from pydantic import BaseModel

from volve_osdu.config import relative
from volve_osdu.extract.curves import CurveMapping
from volve_osdu.facts import Fact, Provenance
from volve_osdu.ingest.las import LasLog
from volve_osdu.ingest.wellpath import WellPath
from volve_osdu.osdu.ids import record_id as make_id
from volve_osdu.osdu.ids import reference, reference_data_id, wellbore_code

KINDS = {
    "Organisation": "osdu:wks:master-data--Organisation:1.2.0",
    "Field": "osdu:wks:master-data--Field:1.1.0",
    "Well": "osdu:wks:master-data--Well:1.5.0",
    "Wellbore": "osdu:wks:master-data--Wellbore:1.5.1",
    "WellLog": "osdu:wks:work-product-component--WellLog:1.5.0",
    "WellboreTrajectory": "osdu:wks:work-product-component--WellboreTrajectory:1.4.0",
    "File.Generic": "osdu:wks:dataset--File.Generic:1.0.0",
}
MODELS: dict[str, type[BaseModel]] = {
    "Organisation": OrganisationData,
    "Field": FieldData,
    "Well": WellData,
    "Wellbore": WellboreData,
    "WellLog": WellLogData,
    "WellboreTrajectory": TrajectoryData,
    "File.Generic": FileGenericData,
}

# Placeholders, as in Equinor's samples. A real OSDU instance assigns its own groups and tags.
ACL = {
    "owners": ["data.default.owners@volve.example.com"],
    "viewers": ["data.default.viewers@volve.example.com"],
}
LEGAL = {"legaltags": ["volve-equinor-open-data-licence"], "otherRelevantDataCountries": ["NO"]}

# LAS LAT/LON are taken as ED50 (verified against NPD, docs/architecture.md).
CRS_CODE = "Geographic2D:EPSG::4230"
CRS_ASSUMPTION = "assumption: LAS LAT/LON are ED50 (EPSG:4230), see docs/architecture.md"

# Well path column -> OSDU UnitOfMeasure code.
STATION_UNITS = {
    "md_m": "m",
    "inclination_deg": "dega",
    "azimuth_deg": "dega",
    "tvd_m": "m",
    "offset_ew_m": "m",
    "offset_ns_m": "m",
    "x_m": "m",
    "y_m": "m",
    "dls_deg_per_30m": "1/30 dega/m",
}


@dataclass
class Record:
    """One OSDU record plus the provenance of every field we filled in its `data` block."""

    type: str  # key of KINDS, e.g. "Wellbore"
    id: str
    data: dict[str, Any]
    provenance: dict[str, list[Provenance]] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return KINDS[self.type]

    @property
    def ref(self) -> str:
        return reference(self.id)

    def set(self, path: str, value: Any, *sources: Provenance) -> None:
        """Set a top-level data field (or register a nested path) with its sources."""
        if value is None:
            return
        if "." not in path and "[" not in path:
            self.data[path] = value
        self.provenance.setdefault(path, []).extend(sources)

    def to_json(self) -> dict[str, Any]:
        """The OSDU record. The Pydantic model checks types; jsonschema checks the rest later."""
        model = MODELS[self.type].model_validate(self.data)
        return {
            "id": self.id,
            "kind": self.kind,
            "acl": ACL,
            "legal": LEGAL,
            "data": model.model_dump(by_alias=True, exclude_none=True, mode="json"),
        }


class Builder:
    """Builds the records of one wellbore. Holds the namespace and CRS details it needs."""

    def __init__(self, namespace: str, crs_persistable_reference: str | None) -> None:
        self.ns = namespace
        self.crs_persistable_reference = crs_persistable_reference

    def ref_data(self, ref_type: str, code: str) -> str:
        if ref_type == "CoordinateReferenceSystem":
            return f"{self.ns}:reference-data--{ref_type}:{code}:"  # CRS codes keep their ':'
        return reference_data_id(self.ns, ref_type, code)

    def organisation(self, name: Fact) -> Record:
        code = re.sub(r"[^\w\-.]+", "-", str(name.value).strip()).strip("-").upper()
        rec = Record("Organisation", make_id(self.ns, "master-data--Organisation", code), {})
        rec.set("OrganisationName", name.value, *name.provenance)
        return rec

    def field(self, name: Fact) -> Record:
        code = re.sub(r"[^\w\-.]+", "-", str(name.value).strip()).strip("-").upper()
        rec = Record("Field", make_id(self.ns, "master-data--Field", code), {})
        rec.set("FieldName", name.value, *name.provenance)
        return rec

    def well(
        self,
        well_name: Fact,
        facts: dict[str, Fact],
        operator: Record | None,
        field_rec: Record | None,
    ) -> Record:
        rec = Record(
            "Well",
            make_id(self.ns, "master-data--Well", wellbore_code(str(well_name.value))),
            {},
        )
        rec.set("FacilityName", well_name.value, *well_name.provenance)
        self._common_facility(rec, operator, field_rec)

        lat, lon = facts.get("surface_latitude_deg"), facts.get("surface_longitude_deg")
        if lat and lon and lat.value is not None and lon.value is not None:
            if self.crs_persistable_reference is None:
                raise ValueError("CRS persistable reference missing from the reference list")
            location = {
                "AsIngestedCoordinates": {
                    "type": "AnyCrsFeatureCollection",
                    "CoordinateReferenceSystemID": self.ref_data(
                        "CoordinateReferenceSystem", CRS_CODE
                    ),
                    "persistableReferenceCrs": self.crs_persistable_reference,
                    "features": [
                        {
                            "type": "AnyCrsFeature",
                            "properties": {},
                            "geometry": {
                                "type": "AnyCrsPoint",
                                "coordinates": [lon.value, lat.value],
                            },
                        }
                    ],
                }
            }
            rec.set(
                "SpatialLocation",
                location,
                *lat.provenance,
                *lon.provenance,
                _derived(CRS_ASSUMPTION),
            )
        return rec

    def wellbore(
        self,
        name: Fact,
        aliases: list[tuple[str, Provenance]],
        well: Record,
        facts: dict[str, Fact],
        operator: Record | None,
        field_rec: Record | None,
        trajectory: Record | None,
    ) -> Record:
        code = wellbore_code(str(name.value))
        rec = Record("Wellbore", make_id(self.ns, "master-data--Wellbore", code), {})
        rec.set("FacilityName", name.value, *name.provenance)
        alias_values = []
        for alias, prov in aliases:
            if alias != name.value and alias not in [a["AliasName"] for a in alias_values]:
                alias_values.append({"AliasName": alias})
                rec.provenance.setdefault(f"NameAliases[{len(alias_values) - 1}]", []).append(prov)
        if alias_values:
            rec.data["NameAliases"] = alias_values
        rec.set("WellID", well.ref, _derived("rule: a sidetrack belongs to its parent's well"))
        self._common_facility(rec, operator, field_rec)

        kickoff = facts.get("kickoff_wellbore_name")
        if kickoff and kickoff.value:
            parent = make_id(self.ns, "master-data--Wellbore", wellbore_code(str(kickoff.value)))
            rec.set("KickOffWellbore", reference(parent), *kickoff.provenance)

        measurements = []
        for vm_id, fact_name, vm_type, path in (
            ("KB", "kb_elevation_m", "KellyBushing", "ELEV"),
            ("TD", "td_md_m", "TotalDepth", "MeasuredDepth"),
            ("KOP", "kop_md_m", "KickOffPoint", "MeasuredDepth"),
        ):
            fact = facts.get(fact_name)
            if not fact or fact.value is None:
                continue
            vm: dict[str, Any] = {
                "VerticalMeasurementID": vm_id,
                "VerticalMeasurement": fact.value,
                "VerticalMeasurementTypeID": self.ref_data("VerticalMeasurementType", vm_type),
                "VerticalMeasurementPathID": self.ref_data("VerticalMeasurementPath", path),
                "VerticalMeasurementUnitOfMeasureID": self.ref_data("UnitOfMeasure", "m"),
            }
            if vm_id != "KB" and facts.get("kb_elevation_m"):
                vm["VerticalReferenceID"] = "KB"  # the reports quote depths as "m MD RKB"
            rec.provenance[f"VerticalMeasurements[{len(measurements)}]"] = list(fact.provenance)
            measurements.append(vm)
        if measurements:
            rec.data["VerticalMeasurements"] = measurements
            if measurements[0]["VerticalMeasurementID"] == "KB":
                rec.set("DefaultVerticalMeasurementID", "KB", _derived("KB is the depth datum"))

        if trajectory is not None:
            rec.set(
                "DefinitiveTrajectoryID",
                trajectory.ref,
                _derived("the only actual (non-plan) well path for this wellbore"),
            )
        return rec

    def dataset(self, code: str, file_source: str, size: int, md5: str, name: str) -> Record:
        rec = Record("File.Generic", make_id(self.ns, "dataset--File.Generic", code), {})
        rec.set("Name", name, _derived("bulk file written by this pipeline"))
        rec.set(
            "DatasetProperties",
            {
                "FileSourceInfo": {
                    "FileSource": file_source,
                    "Name": name,
                    "FileSize": str(size),
                    "Checksum": md5,
                    "ChecksumAlgorithm": "MD5",
                }
            },
            _derived("bulk file written by this pipeline"),
        )
        return rec

    def well_log(
        self,
        log: LasLog,
        wellbore: Record,
        mappings: list[CurveMapping],
        dataset: Record,
        depth_scale: float,
    ) -> Record:
        """`depth_scale` converts the LAS depth unit to metres (1.0 or 0.3048)."""
        code = f"{wellbore.id.rsplit(':', 1)[1]}-{_safe(log.path.stem)}"
        rec = Record("WellLog", make_id(self.ns, "work-product-component--WellLog", code), {})
        src = relative(log.path)

        def las(locator: str) -> Provenance:
            return Provenance(source_file=src, locator=locator, method="parsed")

        rec.set("Name", log.path.name, las("file name"))
        rec.set("WellboreID", wellbore.ref, _derived("file belongs to this wellbore's bundle"))
        rec.set("Datasets", [dataset.ref], _derived("curve values written as Parquet"))
        for key, mnemonic in (
            ("TopMeasuredDepth", "STRT"),
            ("SamplingStart", "STRT"),
            ("BottomMeasuredDepth", "STOP"),
            ("SamplingStop", "STOP"),
            ("SamplingInterval", "STEP"),
        ):
            value = log.header_value(mnemonic)
            if isinstance(value, float):
                rec.set(key, round(value * depth_scale, 4), las(f"LAS:~Well/{mnemonic}"))
        null = log.header_value("NULL")
        if null is not None:
            rec.set("NullValue", str(null), las("LAS:~Well/NULL"))
        rec.set("ReferenceCurveID", log.data.index.name, las("LAS:~Curve first curve"))

        mapping_by_mnemonic = {m.mnemonic: m for m in mappings}
        curves = []
        for curve in log.curves:
            mapping = mapping_by_mnemonic.get(curve.mnemonic)
            item: dict[str, Any] = {
                "CurveID": curve.mnemonic,
                "Mnemonic": curve.mnemonic,
                "CurveDescription": curve.description or None,
                "NumberOfColumns": 1,
                "DepthUnit": self.ref_data("UnitOfMeasure", "m"),
            }
            if curve.top_depth is not None and curve.base_depth is not None:
                item["TopDepth"] = round(curve.top_depth * depth_scale, 4)
                item["BaseDepth"] = round(curve.base_depth * depth_scale, 4)
            sources = [las(f"LAS:~Curve/{curve.mnemonic}")]
            if mapping and mapping.unit_code:
                item["CurveUnit"] = self.ref_data("UnitOfMeasure", mapping.unit_code)
            if mapping and mapping.family:
                item["LogCurveFamilyID"] = self.ref_data("LogCurveFamily", mapping.family)
            if mapping and (mapping.unit_code or mapping.family):
                sources.append(_derived(f"curve mapping ({mapping.method})"))
            rec.provenance[f"Curves[{len(curves)}]"] = sources
            curves.append({k: v for k, v in item.items() if v is not None})
        rec.data["Curves"] = curves
        return rec

    def trajectory(
        self, wellpath: WellPath, wellbore: Record, kb: Fact | None, dataset: Record
    ) -> Record:
        code = f"{wellbore.id.rsplit(':', 1)[1]}-{_safe(wellpath.path.name)}"
        rec = Record(
            "WellboreTrajectory",
            make_id(self.ns, "work-product-component--WellboreTrajectory", code),
            {},
        )
        src = relative(wellpath.path)

        def wp(locator: str) -> Provenance:
            return Provenance(source_file=src, locator=locator, method="parsed")

        rec.set("Name", wellpath.path.name, wp("file name"))
        rec.set("WellboreID", wellbore.ref, _derived("well path assigned to this wellbore"))
        rec.set("Datasets", [dataset.ref], _derived("stations written as Parquet"))
        rec.set("TopDepthMeasuredDepth", wellpath.top_md, wp("WELLPATH:MD row 0"))
        rec.set(
            "BaseDepthMeasuredDepth",
            wellpath.base_md,
            wp(f"WELLPATH:MD row {len(wellpath.stations) - 1}"),
        )
        vm: dict[str, Any] = {
            "VerticalMeasurementTypeID": self.ref_data("VerticalMeasurementType", "KellyBushing"),
            "VerticalMeasurementPathID": self.ref_data("VerticalMeasurementPath", "ELEV"),
            "VerticalMeasurementUnitOfMeasureID": self.ref_data("UnitOfMeasure", "m"),
        }
        sources = [wp("WELLPATH:unit line 'm RKB'")]
        if kb and kb.value is not None:
            vm["VerticalMeasurement"] = kb.value
            sources += kb.provenance
        rec.set("VerticalMeasurement", vm, *sources)
        rec.set(
            "AvailableTrajectoryStationProperties",
            [
                {"Name": col, "StationPropertyUnitID": self.ref_data("UnitOfMeasure", unit)}
                for col, unit in STATION_UNITS.items()
                if col in wellpath.stations.columns
            ],
            wp("WELLPATH:header and unit lines"),
        )
        rec.set("IsDefinitive", not wellpath.is_plan, _derived("file name is not a plan"))
        return rec

    @staticmethod
    def _common_facility(rec: Record, operator: Record | None, field_rec: Record | None) -> None:
        if operator is not None:
            rec.set(
                "CurrentOperatorID",
                operator.ref,
                *operator.provenance.get("OrganisationName", []),
            )
        if field_rec is not None:
            rec.set(
                "GeoContexts",
                [{"FieldID": field_rec.ref, "GeoTypeID": "Field"}],
                *field_rec.provenance.get("FieldName", []),
            )


def _derived(locator: str) -> Provenance:
    return Provenance(source_file="(pipeline)", locator=locator, method="derived")


def _safe(text: str) -> str:
    return re.sub(r"[^\w\-.]+", "-", text).strip("-")
