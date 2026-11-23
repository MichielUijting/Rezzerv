"""Receipt file staging contracts independent of a database test harness.

Authoritative destructive account integration uses isolated PostgreSQL in the
existing consumer_account_deletion_selftest; this unit test changes only files
in pytest-provided temporary storage, never a user's data.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import consumer_account_file_deletion_service as deletion
from app.services.consumer_account_file_deletion_service import (
    AccountFileDeletionConflict,
    HouseholdFileStage,
    household_file_paths,
)


class _ReceiptPathsConnection:
    """Read-only fake of the single metadata query used by the file stage."""

    def __init__(self, paths_by_household: dict[str, list[Path]]) -> None:
        self.paths_by_household = paths_by_household

    def execute(self, statement, parameters):
        assert "SELECT storage_path FROM raw_receipts" in str(statement)
        household = str(parameters["hid"])
        return SimpleNamespace(
            scalars=lambda: [str(p) for p in self.paths_by_household.get(household, [])],
        )


def _fixture(tmp_path: Path, monkeypatch):
    raw = tmp_path / "receipts" / "raw"
    retailer = tmp_path / "retailer-receipts" / "raw"
    monkeypatch.setenv("RECEIPT_STORAGE_ROOT", str(raw))
    monkeypatch.setenv("RETAILER_RECEIPT_STORAGE_ROOT", str(retailer))
    # The actual DML and PostgreSQL transactional assertions run in the
    # isolated PostgreSQL integration contract, not in this filesystem test.
    inspector = SimpleNamespace(
        has_table=lambda name: name == "raw_receipts",
        get_columns=lambda name: [{"name": "household_id"}, {"name": "storage_path"}],
    )
    monkeypatch.setattr(deletion, "inspect", lambda _: inspector)
    return raw, retailer


def test_retailer_and_standard_receipts_stage_restore_and_finalize(tmp_path, monkeypatch):
    raw, retailer = _fixture(tmp_path, monkeypatch)
    a = raw / "sole" / "2026" / "11" / "photo.jpg"
    b = retailer / "sole" / "2026" / "11" / "ah.json"
    other = retailer / "shared" / "2026" / "11" / "shared.json"
    for item in (a, b, other):
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("isolated test only", encoding="utf-8")
    conn = _ReceiptPathsConnection({"sole": [a, b], "shared": [other]})
    assert household_file_paths("sole")[3] == retailer / "sole"
    stage = HouseholdFileStage()
    stage.stage(conn, ["sole"])
    assert not a.exists() and not b.exists()
    assert len(stage._staged) == 2  # two independent volume-local journals
    assert other.is_file()
    stage.restore()
    assert a.is_file() and b.is_file() and other.is_file()
    stage = HouseholdFileStage()
    stage.stage(conn, ["sole"])
    stage.finalize()
    assert not a.exists() and not b.exists()
    assert other.is_file()


def test_other_household_path_never_authorized_for_target(tmp_path, monkeypatch):
    _, retailer = _fixture(tmp_path, monkeypatch)
    foreign = retailer / "unrelated" / "receipt.json"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("do not remove", encoding="utf-8")
    conn = _ReceiptPathsConnection({"sole": [foreign]})
    with pytest.raises(AccountFileDeletionConflict, match="buiten de eigen huishoudmap"):
        HouseholdFileStage().stage(conn, ["sole"])
    assert foreign.read_text(encoding="utf-8") == "do not remove"


def test_symlinks_are_not_followed_in_retailer_root(tmp_path, monkeypatch):
    _, retailer = _fixture(tmp_path, monkeypatch)
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("safe", encoding="utf-8")
    household = retailer / "sole"
    household.mkdir(parents=True)
    (household / "alias").symlink_to(external, target_is_directory=True)
    conn = _ReceiptPathsConnection({})
    with pytest.raises(AccountFileDeletionConflict, match="gekoppeld|Symbolische koppeling"):
        HouseholdFileStage().stage(conn, ["sole"])
    assert (external / "keep.txt").is_file()
