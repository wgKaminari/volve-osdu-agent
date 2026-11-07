"""Pinned OSDU reference values (data-definitions v0.30.1), loaded from data/raw/reference/."""

import json
from functools import cache
from pathlib import Path

PLACEHOLDER = "{{NAMESPACE}}"


@cache
def load_reference_ids(path: Path, namespace: str) -> frozenset[str]:
    """All reference IDs in one reference-data manifest, with the namespace filled in.

    The files store IDs without a version suffix; we add ':' so they compare equal to the
    references we write into records (see ids.reference_data_id).
    """
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(
        item["id"].replace(PLACEHOLDER, namespace) + ":" for item in manifest["ReferenceData"]
    )
