"""Checks that configs/wells.yaml is consistent and matches the downloaded files."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "configs" / "wells.yaml"
RAW_DATA = ROOT / "data" / "raw" / "spwla_volve"


def load_config() -> dict:
    with CONFIG.open() as f:
        return yaml.safe_load(f)


def test_has_13_mvp_wellbores() -> None:
    cfg = load_config()
    assert len(cfg["wellbores"]) == 13


def test_canonical_names_are_unique() -> None:
    names = [w["canonical_name"] for w in load_config()["wellbores"]]
    assert len(names) == len(set(names))


def test_every_wellbore_has_required_keys() -> None:
    required = {"canonical_name", "folder", "las", "pdf", "wellpath", "dlis", "other_files"}
    for w in load_config()["wellbores"]:
        assert required <= w.keys(), f"{w.get('folder')} is missing {required - w.keys()}"


@pytest.mark.skipif(
    not RAW_DATA.exists(),
    reason="raw data not downloaded (run scripts/download_data.sh)",
)
def test_all_listed_files_exist_on_disk() -> None:
    cfg = load_config()
    bundle_root = ROOT / cfg["bundle_root"]
    wellpath_root = ROOT / cfg["wellpath_root"]
    missing: list[str] = []

    for w in cfg["wellbores"]:
        folder = bundle_root / w["folder"]
        files = w["las"] + w["dlis"] + w["other_files"]
        if w["pdf"]:
            files.append(w["pdf"])
        for name in files:
            if not (folder / name).is_file():
                missing.append(f"{w['folder']}/{name}")

        if w["wellpath"] and not (wellpath_root / w["wellpath"]).is_file():
            missing.append(f"wellpaths/{w['wellpath']}")

    assert missing == [], f"missing files: {missing}"
