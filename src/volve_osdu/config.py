"""Project settings and the wellbore bundles from configs/wells.yaml."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WELLS_CONFIG = ROOT / "configs" / "wells.yaml"
RAW = ROOT / "data" / "raw"
REFERENCE_DIR = RAW / "reference"
RECORD_SCHEMAS = RAW / "osdu-python-models" / "schemas" / "M27.1"
MANIFEST_SCHEMAS = RAW / "osdu-mcp-poc" / "schemas"


def namespace() -> str:
    """OSDU data partition namespace used in every ID (env OSDU_NAMESPACE, default "volve")."""
    return os.environ.get("OSDU_NAMESPACE", "volve")


@dataclass(frozen=True)
class Bundle:
    """The input files for one wellbore. `canonical_name` is for scoring and output folders only:
    the systems must work the name out from the files themselves."""

    canonical_name: str
    folder: Path
    las: list[Path]
    pdf: Path | None
    wellpath: Path | None


def load_bundles(config: Path = WELLS_CONFIG) -> list[Bundle]:
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    bundle_root = ROOT / cfg["bundle_root"]
    wellpath_root = ROOT / cfg["wellpath_root"]
    bundles = []
    for w in cfg["wellbores"]:
        folder = bundle_root / w["folder"]
        bundles.append(
            Bundle(
                canonical_name=w["canonical_name"],
                folder=folder,
                las=[folder / name for name in w["las"]],
                pdf=folder / w["pdf"] if w["pdf"] else None,
                wellpath=wellpath_root / w["wellpath"] if w["wellpath"] else None,
            )
        )
    return bundles


def find_bundle(name: str, config: Path = WELLS_CONFIG) -> Bundle:
    """Look up a bundle by canonical name ("15/9-F-12") or folder name ("15_9-F12")."""
    for bundle in load_bundles(config):
        if name in (bundle.canonical_name, bundle.folder.name):
            return bundle
    raise KeyError(f"unknown wellbore {name!r} (see configs/wells.yaml)")


def relative(path: Path) -> str:
    """Path as written into provenance: relative to the repo, so outputs don't leak home dirs."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()
