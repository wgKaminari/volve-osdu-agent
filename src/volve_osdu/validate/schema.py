"""Rule 1: JSON-schema validation against the pinned OSDU schemas (draft-07, relative $refs).

The schemas reference each other by URL (https://schema.osdu.opengroup.org/json/abstract/...).
We resolve those URLs to the local pinned copies, so validation never touches the network.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from volve_osdu.config import MANIFEST_SCHEMAS, RECORD_SCHEMAS
from volve_osdu.facts import Issue

SCHEMA_BASE = "https://schema.osdu.opengroup.org/json/"
MAX_ERRORS_PER_RECORD = 20


def schema_path(kind: str, root: Path = RECORD_SCHEMAS) -> Path:
    """ "osdu:wks:master-data--Well:1.5.0" -> <root>/master-data/Well.1.5.0.json."""
    _authority, _source, entity, version = kind.split(":")
    group, name = entity.split("--", 1)
    return root / group / f"{name}.{version}.json"


@cache
def _validator(path: Path, root: Path) -> jsonschema.Draft7Validator:
    def retrieve(uri: str) -> Resource:
        if not uri.startswith(SCHEMA_BASE):
            raise LookupError(f"refusing to fetch non-OSDU schema {uri}")
        local = root / uri.removeprefix(SCHEMA_BASE)
        return Resource.from_contents(_load(local), default_specification=DRAFT7)

    registry: Registry = Registry(retrieve=retrieve)  # type: ignore[call-arg]
    return jsonschema.Draft7Validator(_load(path), registry=registry)


@cache
def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_record(record: dict[str, Any], root: Path = RECORD_SCHEMAS) -> list[Issue]:
    path = schema_path(record["kind"], root)
    if not path.exists():
        return [
            Issue(
                rule=1,
                severity="error",
                record_id=record.get("id"),
                message=f"no schema {path.name}",
            )
        ]
    return _issues(_validator(path, root), record, record.get("id"))


def validate_manifest(manifest: dict[str, Any], root: Path = MANIFEST_SCHEMAS) -> list[Issue]:
    path = root / "manifest" / "Manifest.1.0.0.json"
    return _issues(_validator(path, root), manifest, "manifest")


def _issues(
    validator: jsonschema.Draft7Validator, doc: dict[str, Any], rid: str | None
) -> list[Issue]:
    issues = []
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))[
        :MAX_ERRORS_PER_RECORD
    ]:
        issues.append(
            Issue(
                rule=1,
                severity="error",
                record_id=rid,
                path=".".join(str(p) for p in error.absolute_path) or None,
                message=error.message[:300],
            )
        )
    return issues
