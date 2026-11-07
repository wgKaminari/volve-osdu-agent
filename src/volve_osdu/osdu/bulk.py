"""Bulk values (curve samples, trajectory stations) as Parquet files next to the manifest.

OSDU keeps bulk data out of the work-product-component record; the record points to a
dataset--File.Generic record that describes the file (name, size, MD5 checksum).
"""

import hashlib
from pathlib import Path

import pandas as pd


def write_parquet(frame: pd.DataFrame, path: Path) -> tuple[int, str]:
    """Write `frame` and return (size in bytes, MD5 hex digest) of the written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    data = path.read_bytes()
    return len(data), hashlib.md5(data).hexdigest()
