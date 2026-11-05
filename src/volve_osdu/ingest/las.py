"""LAS reader: header items, curve metadata and curve data from a LAS 2.0 file (via lasio)."""

from dataclasses import dataclass
from pathlib import Path

import lasio
import pandas as pd


@dataclass(frozen=True)
class HeaderItem:
    """One line of the LAS ~Well section, e.g. ELEV .M 54.9 : SURFACE ELEV."""

    mnemonic: str
    unit: str
    value: str | float | None
    description: str


@dataclass(frozen=True)
class CurveInfo:
    """One curve from the ~Curve section, plus the depth range where it has real (non-null) data."""

    mnemonic: str
    unit: str
    description: str
    n_valid: int
    top_depth: float | None
    base_depth: float | None


@dataclass(frozen=True)
class LasLog:
    """A parsed LAS file. `data` is indexed by depth; null values are already NaN."""

    path: Path
    well: dict[str, HeaderItem]
    depth_unit: str
    curves: list[CurveInfo]
    data: pd.DataFrame

    def header_value(self, mnemonic: str) -> str | float | None:
        """Value of a ~Well item, or None if the item is missing or empty."""
        item = self.well.get(mnemonic)
        if item is None or item.value in ("", None):
            return None
        return item.value


def read_las(path: Path) -> LasLog:
    """Read a LAS file. Depth is the index; the depth curve itself is not listed in `curves`."""
    las = lasio.read(str(path))
    data = las.df()  # lasio replaces the NULL value with NaN
    well = {
        item.mnemonic: HeaderItem(
            mnemonic=item.mnemonic,
            unit=item.unit,
            value=_clean(item.value),
            description=item.descr.strip(),
        )
        for item in las.well
    }
    depth_curve, *log_curves = las.curves
    curves = [_curve_info(c, data[c.mnemonic]) for c in log_curves]
    return LasLog(path=path, well=well, depth_unit=depth_curve.unit, curves=curves, data=data)


def _curve_info(curve: lasio.CurveItem, values: pd.Series) -> CurveInfo:
    valid = values.dropna()
    return CurveInfo(
        mnemonic=curve.mnemonic,
        unit=curve.unit,
        description=_curve_description(curve),
        n_valid=len(valid),
        top_depth=float(valid.index.min()) if len(valid) else None,
        base_depth=float(valid.index.max()) if len(valid) else None,
    )


def _curve_description(curve: lasio.CurveItem) -> str:
    """Rebuild the full curve description.

    lasio splits "UNKNOWN : GR:UNKNOWN:rC:NONE:v1" at the *last* colon, giving the API code
    "UNKNOWN : GR:UNKNOWN:rC:NONE" and the description "v1". The real API code ends at the
    *first* colon, so we re-join everything after it.
    """
    value = str(curve.value)
    if ":" in value:
        _api_code, rest = value.split(":", 1)
        return f"{rest.strip()}:{curve.descr.strip()}"
    return curve.descr.strip()


def _clean(value: object) -> str | float | None:
    """Normalize header values: numbers become float, blank strings become None."""
    if isinstance(value, str):
        return value.strip() or None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
