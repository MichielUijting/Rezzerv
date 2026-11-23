"""Crash-recoverable deletion of household receipts from all configured stores.

Standard and digital retailer receipts occupy DIFFERENT Docker volumes. Each
category is staged within its own filesystem before SQL commit. An interrupted
transaction is reconciled from the durable household_registry identity.
No arbitrary storage paths, cross-household folders or symlinks are followed.
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
CATEGORIES = ("raw", "sources", "debug")


class AccountFileDeletionConflict(RuntimeError):
    pass


def _safe_household_id(hid: str) -> str:
    value = str(hid or "")
    if not value or value in {".", "..", "0"} or Path(value).name != value or "/" in value or "\\" in value:
        raise AccountFileDeletionConflict("Ongeldige huishoudidentiteit voor bestandsverwijdering.")
    return value


def _checked_storage_root(env_name: str, default: str) -> Path:
    raw = Path(os.getenv(env_name, default))
    if not raw.is_absolute() or ".." in raw.parts:
        raise AccountFileDeletionConflict("De kassabonopslag heeft geen veilige absolute map.")
    if any(p.is_symlink() for p in (raw, *raw.parents, raw.parent / "sources", raw.parent / "debug")):
        raise AccountFileDeletionConflict("Symbolische koppeling in kassabonopslag; niets verwijderd.")
    return raw


def _root() -> Path:
    return _checked_storage_root("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw")


def _retailer_root() -> Path:
    return _checked_storage_root("RETAILER_RECEIPT_STORAGE_ROOT", "/app/data/retailer-receipts/raw")


def _category_roots(raw_root: Path) -> tuple[tuple[str, Path], ...]:
    primary = (
        ("raw", raw_root),
        ("sources", raw_root.parent / "sources"),
        ("debug", raw_root.parent / "debug"),
    )
    retailer = _retailer_root()
    if retailer == raw_root:
        return primary
    if retailer.parent == raw_root.parent or retailer in raw_root.parents or raw_root in retailer.parents:
        raise AccountFileDeletionConflict("Overlappende kassabonopslagmappen; niets verwijderd.")
    return primary + (
        ("retailer_raw", retailer),
        ("retailer_sources", retailer.parent / "sources"),
        ("retailer_debug", retailer.parent / "debug"),
    )


def _paths(root: Path, hid: str) -> tuple[Path, ...]:
    return tuple(category_root / hid for _, category_root in _category_roots(root))


def household_file_paths(hid: str) -> tuple[Path, ...]:
    """All household-specific physical receipt locations, including retailer."""
    return _paths(_root(), _safe_household_id(hid))


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
                raise AccountFileDeletionConflict("Onbekend of gekoppeld bestand in kassabonopslag.")
    except OSError as exc:
        raise AccountFileDeletionConflict("Kassabonbestanden konden niet veilig worden gecontroleerd.") from exc


def _staging_base(category_root: Path) -> Path:
    # Must be on the SAME mount as category_root / household_id. The original
    # raw folder and digital retailer receipts have distinct Docker volumes.
    return category_root / STAGING_NAME


def _legacy_staging_base(raw_root: Path) -> Path:
    # Recover pre-fix journals produced by the original account deletion path.
    return raw_root.parent / STAGING_NAME


def _write_manifest(folder: Path, ids: list[str]) -> None:
    data = json.dumps({"format": 2, "households": ids}, sort_keys=True)
    temp = folder / "manifest.tmp"
    with temp.open("x", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(folder / "manifest.json")


def _read_manifest(folder: Path) -> tuple[list[str], int]:
    path = folder / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise AccountFileDeletionConflict("Onvolledige verwijderjournal; handmatig onderzoek vereist.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data["households"]
        version = data["format"]
        if version not in (1, 2) or not isinstance(ids, list):
            raise ValueError("unknown journal format")
        normalized = [_safe_household_id(x) for x in ids]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("duplicate household")
        return normalized, int(version)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AccountFileDeletionConflict("Ongeldige verwijderjournal; niets gewist.") from exc


class HouseholdFileStage:
    """One SQL transaction may atomically stage multiple sole-member households."""

    def __init__(self) -> None:
        self.raw_root = _root()
        _category_roots(self.raw_root)  # Validate both roots before touching files.
        self.household_ids: frozenset[str] = frozenset()
        self._staged: list[tuple[Path, Path]] = []

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
                if not candidate.is_absolute() or ".." in candidate.parts:
                    raise AccountFileDeletionConflict("Ongeldig kassabonpad kan niet veilig worden verwijderd.")
                # Lexical containment, not realpath: do NOT follow symbolic links.
                if not any(candidate == base or base in candidate.parents for base in allowed):
                    raise AccountFileDeletionConflict("Kassabonbestand buiten de eigen huishoudmap aangetroffen.")

    def stage(self, conn: Connection, household_ids: list[str]) -> None:
        if self._staged or self.household_ids:
            raise AccountFileDeletionConflict("Bestandsstaging mag niet opnieuw worden gestart.")
        ids = sorted({_safe_household_id(hid) for hid in household_ids})
        self._validate_database_paths(conn, ids)
        roots = _category_roots(self.raw_root)
        for _, category_root in roots:
            for hid in ids:
                _check_tree(category_root / hid)
        self.household_ids = frozenset(ids)
        try:
            for _, category_root in roots:
                if not any((category_root / hid).exists() for hid in ids):
                    continue
                base = _staging_base(category_root)
                if base.is_symlink():
                    raise AccountFileDeletionConflict("Onveilige staging-map.")
                base.mkdir(parents=True, exist_ok=True)
                folder = base / str(uuid.uuid4())
                folder.mkdir(mode=0o700)
                # Record immediately so rollback can remove a partial stage.
                self._staged.append((category_root, folder))
                _write_manifest(folder, ids)
                for hid in ids:
                    source = category_root / hid
                    if source.exists():
                        destination = folder / hid
                        source.rename(destination)  # same-device rename by design
        except Exception:
            self.restore()
            raise

    def restore(self) -> None:
        for category_root, folder in reversed(self._staged):
            for hid in sorted(self.household_ids):
                source = folder / hid
                if source.exists():
                    target = category_root / hid
                    if target.exists() or target.is_symlink():
                        raise AccountFileDeletionConflict(
                            "Herstelconflict: huishoudmap bestaat al; staging blijft behouden."
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(target)
            shutil.rmtree(folder)
        self._staged.clear()

    def finalize(self) -> None:
        for _, folder in self._staged:
            shutil.rmtree(folder)
        self._staged.clear()


def _surviving_households(engine: Engine, ids: list[str]) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT CAST(id AS TEXT) FROM household_registry
            WHERE CAST(id AS TEXT) = ANY(:ids)
        """), {"ids": ids}).scalars().all()
    surviving = set(rows)
    if surviving and surviving != set(ids):
        raise AccountFileDeletionConflict("Inconsistente gedeeltelijke huishoudverwijdering.")
    return surviving


def _restore_legacy_folder(folder: Path, raw_root: Path, ids: list[str]) -> None:
    original_roots = (
        raw_root, raw_root.parent / "sources", raw_root.parent / "debug",
    )
    for hid in sorted(ids):
        for category, category_root in zip(CATEGORIES, original_roots):
            source = folder / category / hid
            if source.exists():
                target = category_root / hid
                if target.exists() or target.is_symlink():
                    raise AccountFileDeletionConflict(
                        "Herstelconflict: huishoudmap bestaat al; staging blijft behouden."
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
    shutil.rmtree(folder)


def reconcile_household_file_staging(engine: Engine) -> int:
    """Restore rolled-back accounts, or finalize committed deletion on restart."""
    raw_root = _root()
    categories = _category_roots(raw_root)
    sources = [(category_root, _staging_base(category_root), 2) for _, category_root in categories]
    sources.append((raw_root, _legacy_staging_base(raw_root), 1))
    recovered = 0
    for category_root, base, expected_version in sources:
        if not base.exists():
            continue
        if base.is_symlink() or not base.is_dir():
            raise AccountFileDeletionConflict("Onveilige accountverwijderjournal.")
        for folder in sorted(base.iterdir()):
            if folder.is_symlink() or not folder.is_dir():
                raise AccountFileDeletionConflict("Onbekend object in accountverwijderjournal.")
            ids, version = _read_manifest(folder)
            if version != expected_version:
                raise AccountFileDeletionConflict("Onverwachte accountverwijderjournal-versie.")
            _check_tree(folder)
            surviving = _surviving_households(engine, ids)
            if expected_version == 1:
                if surviving:
                    _restore_legacy_folder(folder, raw_root, ids)
                else:
                    shutil.rmtree(folder)
            else:
                stage = HouseholdFileStage()
                stage.household_ids = frozenset(ids)
                stage._staged = [(category_root, folder)]
                if surviving:
                    stage.restore()
                else:
                    stage.finalize()
            recovered += 1
    return recovered
