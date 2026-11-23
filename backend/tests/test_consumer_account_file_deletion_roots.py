"""Isolation contracts for physical receipt deletion across both storage roots.

All test files live under pytest's temporary directory; no user database/files.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.services.consumer_account_file_deletion_service import (
    AccountFileDeletionConflict,
    HouseholdFileStage,
    household_file_paths,
)


def _fixture(tmp_path: Path, monkeypatch):
    raw = tmp_path / "receipts" / "raw"
    retailer = tmp_path / "retailer-receipts" / "raw"
    monkeypatch.setenv("RECEIPT_STORAGE_ROOT", str(raw))
    monkeypatch.setenv("RETAILER_RECEIPT_STORAGE_ROOT", str(retailer))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE raw_receipts (household_id TEXT, storage_path TEXT)"
        ))
    return engine, raw, retailer


def test_retailer_and_standard_receipts_stage_restore_and_finalize(tmp_path, monkeypatch):
    engine, raw, retailer = _fixture(tmp_path, monkeypatch)
    a = raw / "sole" / "2026" / "11" / "photo.jpg"
    b = retailer / "sole" / "2026" / "11" / "ah.json"
    other = retailer / "shared" / "2026" / "11" / "shared.json"
    for item in (a, b, other):
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("isolated test only", encoding="utf-8")
    with engine.begin() as conn:
        for item, hid in ((a, "sole"), (b, "sole"), (other, "shared")):
            conn.execute(text(
                "INSERT INTO raw_receipts(household_id, storage_path) "
                "VALUES (:hid, :path)"
            ), {"hid": hid, "path": str(item)})
    assert b in household_file_paths("sole")[3].parents or (
        household_file_paths("sole")[3] == retailer / "sole"
    )
    stage = HouseholdFileStage()
    with engine.begin() as conn:
        stage.stage(conn, ["sole"])
    assert not a.exists() and not b.exists()
    assert other.is_file()
    stage.restore()
    assert a.is_file() and b.is_file() and other.is_file()
    stage = HouseholdFileStage()
    with engine.begin() as conn:
        stage.stage(conn, ["sole"])
    stage.finalize()
    assert not a.exists() and not b.exists()
    assert other.is_file()
    engine.dispose()


def test_other_households_path_never_authorized_for_target(tmp_path, monkeypatch):
    engine, raw, retailer = _fixture(tmp_path, monkeypatch)
    foreign = retailer / "unrelated" / "receipt.json"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("do not remove", encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO raw_receipts(household_id, storage_path) "
            "VALUES ('sole', :path)"
        ), {"path": str(foreign)})
    with engine.begin() as conn:
        with pytest.raises(AccountFileDeletionConflict, match="buiten de eigen huishoudmap"):
            HouseholdFileStage().stage(conn, ["sole"])
    assert foreign.read_text(encoding="utf-8") == "do not remove"
    engine.dispose()


def test_symlinks_are_not_followed_in_retailer_root(tmp_path, monkeypatch):
    engine, _, retailer = _fixture(tmp_path, monkeypatch)
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("safe", encoding="utf-8")
    household = retailer / "sole"
    household.mkdir(parents=True)
    (household / "alias").symlink_to(external, target_is_directory=True)
    with engine.begin() as conn:
        with pytest.raises(AccountFileDeletionConflict, match="Symbolische koppeling"):
            HouseholdFileStage().stage(conn, ["sole"])
    assert (external / "keep.txt").is_file()
    engine.dispose()
