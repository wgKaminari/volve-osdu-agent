"""OSDU identifiers for records and references.

Record IDs:    <namespace>:master-data--Wellbore:NO-15-9-F-1-A
References:    <namespace>:master-data--Wellbore:NO-15-9-F-1-A:     (trailing ":" = latest version)
Reference data: <namespace>:reference-data--UnitOfMeasure:gAPI:
"""

import re
from urllib.parse import quote

# Characters allowed in the last part of an OSDU record ID (schema pattern [\w\-\.\:\%]+).
_UNSAFE = re.compile(r"[^\w\-.]+")


def wellbore_code(canonical_name: str) -> str:
    """Turn a wellbore name into an ID-safe code: "15/9-F-1 A" -> "NO-15-9-F-1-A"."""
    return "NO-" + _UNSAFE.sub("-", canonical_name.strip()).strip("-")


def record_id(namespace: str, entity: str, code: str) -> str:
    """ID of a record we create: ("volve", "master-data--Wellbore", "NO-15-9-F-12")."""
    return f"{namespace}:{entity}:{code}"


def reference(record: str) -> str:
    """Turn a record ID into a reference to its latest version (OSDU appends ':')."""
    return f"{record}:"


def reference_data_id(namespace: str, ref_type: str, code: str) -> str:
    """ID of a reference value, e.g. ("volve", "UnitOfMeasure", "gAPI").

    Codes are percent-encoded the same way as in the OSDU reference lists,
    so "Gamma Ray" becomes "Gamma%20Ray".
    """
    return f"{namespace}:reference-data--{ref_type}:{quote(code, safe='')}:"
