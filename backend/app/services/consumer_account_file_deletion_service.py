"""Crash-recoverable staging of a sole household's raw receipt files.

Only household-specific paths under the configured receipt root are touched.
The caller commits SQL before permanently removing the staged directories.
Every staging directory carries an fsynced manifest. On startup, recovery
restores it if the household still exists; otherwise it finishes the purge.
Never sweep arbitrary application folders or follow symlinks.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

STAGING_NAME = ".account_deletion_staging"


class AccountFileDeletionConflict(RuntimeError):
    pass


def _safe_household_id(hid: str) -> str:
    value = str(hid or "")
    if not value or value in {".", "..", "0"} or Path(value).name != value or "/" in value or "\\" in value:
        raise AccountFileDeletionConflict("Ongeldige huishoudidentiteit voor bestandsverwijdering.")
    return value


def _paths(root: Path, hid: str) -> tuple[Path, Path]:
    return root / hid, root.parent / "sources" / hid


def _check_tree(path: Path) -> None:
    if path.is_symlink():
        raise AccountFileDeletionConflict("Symbolische koppeling in kassabonopslag; niets verwijderd.")
    if not path.exists():
        return
    if not path.is_dir():
        raise AccountFileDeletionConflict("Kassabonopslag is geen map; niets verwijderd.")
    try:
        for entry in path.rglob("*"):
            if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                raise AccountFileDeletionConflict("Onbekend bestandstype in kassabonopslag.")
    except OSError as exc:
        raise AccountFileDeletionConflict("Kassabonbestanden konden niet veilig worden gecontroleerd.") from exc


def _root() -> Path:
    raw = Path(os.getenv("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw"))
    if not raw.is_absolute() or raw.is_symlink():
        raise AccountFileDeletionConflict("De kassabonopslag heeft geen veilige absolute map.")
    return raw


def _staging_base(raw_root: Path) -> Path:
    return raw_root.parent / STAGING_NAME


def _write_manifest(folder: Path, ids: list[str]) -> None:
    data = json.dumps({"format": 1, "households": ids}, sort_keys=True)
    temp = folder / "manifest.tmp"
    with temp.open("x", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(folder / "manifest.json")


def _read_manifest(folder: Path) -> list[str]:
    path = folder / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise AccountFileDeletionConflict("Onvolledige verwijderjournal; handmatig onderzoek vereist.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data["households"]
        if data["format"] != 1 or not isinstance(ids, list):
            raise ValueError("unknown journal format")
        normalized = [_safe_household_id(x) for x in ids]
        if len(normalized) != len(set(normalized)):
            raise ValueError("duplicate household")
        return normalized
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AccountFileDeletionConflict("Ongeldige verwijderjournal; niets gewist.") from exc


class HouseholdFileStage:
    """One DB transaction may stage several *sole-member* households atomically."""

    def __init__(self) -> None:
        self.raw_root = _root()
        self.household_ids: frozenset[str] = frozenset()
        self.folder: Path | None = None

    def _validate_database_paths(self, conn: Connection, hids: list[str]) -> None:
        inspector = inspect(conn)
        if not inspector.has_table("raw_receipts"):
            return
        cols = {v["name"] for v in inspector.get_columns("raw_receipts")}
        if not {"household_id", "storage_path"}.issubset(cols):
            raise AccountFileDeletionConflict("Kassabonbestandskolommen ontbreken.")
        for hid in hids:
            rows = conn.execute(text("""
                SELECT storage_path FROM raw_receipts
                WHERE CAST(household_id AS TEXT)=:hid AND storage_path IS NOT NULL
            """), {"hid": hid}).scalars()
            allowed = _paths(self.raw_root, hid)
            for value in rows:
                filename = str(value or "").strip()
                if not filename:
                    continue
                candidate = Path(filename)
                if not candidate.is_absolute():
                    raise AccountFileDeletionConflict("Relatief kassabonpad kan niet veilig worden verwijderd.")
                # Lexical containment (no following symlinks); check the actual tree separately.
                if not any(candidate == base or base in candidate.parents for base in allowed):
                    raise AccountFileDeletionConflict("Kassabonbestand buiten de eigen huishoudmap aangetroffen.")

    def stage(self, conn: Connection, household_ids: list[str]) -> None:
        if self.folder is not None or self.household_ids:
            raise AccountFileDeletionConflict("Bestandsstaging mag niet opnieuw worden gestart.")
        ids = sorted({_safe_household_id(hid) for hid in household_ids})
        self._validate_database_paths(conn, ids)
        for hid in ids:
            for path in _paths(self.raw_root, hid):
                _check_tree(path)
        self.household_ids = frozenset(ids)
        if not any(path.exists() for hid in ids for path in _paths(self.raw_root, hid)):
            return
        base = _staging_base(self.raw_root)
        base.mkdir(parents=True, exist_ok=True)
        if base.is_symlink():
            raise AccountFileDeletionConflict("Onveilige staging-map.")
        folder = base / str(uuid.uuid4())
        folder.mkdir(mode=0o700)
        self.folder = folder
        _write_manifest(folder, ids)
        try:
            for hid in ids:
                for category, source in zip(("raw", "sources"), _paths(self.raw_root, hid)):
                    if source.exists():
                        destination = folder / category / hid
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        source.rename(destination)
        except Exception:
            self.restore()
            raise

    def restore(self) -> None:
        if self.folder is None:
            return
        folder = self.folder
        for hid in sorted(self.household_ids):
            for category, target in zip(("raw", "sources"), _paths(self.raw_root, hid)):
                source = folder / category / hid
                if source.exists():
                    if target.exists() or target.is_symlink():
                        raise AccountFileDeletionConflict("Herstelconflict: huishoudmap bestaat al; staging blijft behouden.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(target)
        shutil.rmtree(folder)
        self.folder = None

    def finalize(self) -> None:
        if self.folder is not None:
            shutil.rmtree(self.folder)
            self.folder = None


def reconcile_household_file_staging(engine: Engine) -> int:
    """Recover interruptions using the committed PostgreSQL household identity."""
    raw_root = _root()
    base = _staging_base(raw_root)
    if not base.exists():
        return 0
    if base.is_symlink() or not base.is_dir():
        raise AccountFileDeletionConflict("Onveilige accountverwijderjournal.")
    recovered = 0
    for folder in sorted(base.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            raise AccountFileDeletionConflict("Onbekend object in accountverwijderjournal.")
        ids = _read_manifest(folder)
        _check_tree(folder)
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT CAST(id AS TEXT) FROM household_registry
                WHERE CAST(id AS TEXT) = ANY(:ids)
            """), {"ids": ids}).scalars().all()
        surviving = set(rows)
        if surviving and surviving != set(ids):
            raise AccountFileDeletionConflict("Inconsistente gedeeltelijke huishoudverwijdering.")
        stage = HouseholdFileStage()
        stage.household_ids = frozenset(ids)
        stage.folder = folder
        if surviving:
            stage.restore()
        else:
            stage.finalize()
        recovered += 1
    return recovered
