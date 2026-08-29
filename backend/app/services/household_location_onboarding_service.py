from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import inspect, text

_REQUIRED_SPACE_COLUMNS = {"id", "naam", "household_id", "active"}
_REQUIRED_SUBLOCATION_COLUMNS = {"id", "naam", "space_id", "active"}


@dataclass(frozen=True)
class ProvisionedSpace:
    id: str
    name: str


@dataclass(frozen=True)
class ProvisionedSublocation:
    id: str
    name: str
    space_id: str
    space_name: str


def _normalize_name(value: str, *, label: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise ValueError(f"{label} ontbreekt")
    if len(normalized) > 120:
        raise ValueError(f"{label} mag maximaal 120 tekens bevatten")
    return normalized


def ensure_location_foundation(conn) -> None:
    """Validate the Alembic-owned location foundation without schema mutation."""
    inspector = inspect(conn)
    for table_name, required_columns in (
        ("spaces", _REQUIRED_SPACE_COLUMNS),
        ("sublocations", _REQUIRED_SUBLOCATION_COLUMNS),
    ):
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"Canonical location foundation mist {table_name}. "
                "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
            )
        actual_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing = required_columns - actual_columns
        if missing:
            raise RuntimeError(
                f"Canonical location foundation wijkt af: {table_name} mist {sorted(missing)}. "
                "Voer Alembic migrations uit."
            )


def _resolve_or_create_space(conn, *, household_id: str, name: str) -> ProvisionedSpace:
    normalized_name = _normalize_name(name, label="Hoofdlocatie")
    rows = conn.execute(text("""
        SELECT id, naam
        FROM spaces
        WHERE household_id = :household_id
          AND lower(trim(naam)) = lower(trim(:naam))
        ORDER BY id
        LIMIT 2
    """), {
        "household_id": household_id,
        "naam": normalized_name,
    }).mappings().all()

    if len(rows) > 1:
        raise ValueError(f"Hoofdlocatie '{normalized_name}' bestaat dubbel in dit huishouden")

    if rows:
        space_id = str(rows[0].get("id") or "").strip()
        conn.execute(text("""
            UPDATE spaces
            SET naam = :naam, active = :active
            WHERE id = :id AND household_id = :household_id
        """), {
            "id": space_id,
            "household_id": household_id,
            "naam": normalized_name,
            "active": True,
        })
        return ProvisionedSpace(id=space_id, name=normalized_name)

    space_id = str(uuid.uuid4())
    conn.execute(text("""
        INSERT INTO spaces (id, naam, household_id, active)
        VALUES (:id, :naam, :household_id, :active)
    """), {
        "id": space_id,
        "naam": normalized_name,
        "household_id": household_id,
        "active": True,
    })
    return ProvisionedSpace(id=space_id, name=normalized_name)


def _resolve_or_create_sublocation(
    conn,
    *,
    space: ProvisionedSpace,
    name: str,
) -> ProvisionedSublocation:
    normalized_name = _normalize_name(name, label="Sublocatie")
    rows = conn.execute(text("""
        SELECT id, naam
        FROM sublocations
        WHERE space_id = :space_id
          AND lower(trim(naam)) = lower(trim(:naam))
        ORDER BY id
        LIMIT 2
    """), {
        "space_id": space.id,
        "naam": normalized_name,
    }).mappings().all()

    if len(rows) > 1:
        raise ValueError(
            f"Sublocatie '{normalized_name}' bestaat dubbel onder '{space.name}'"
        )

    if rows:
        sublocation_id = str(rows[0].get("id") or "").strip()
        conn.execute(text("""
            UPDATE sublocations
            SET naam = :naam, active = :active
            WHERE id = :id AND space_id = :space_id
        """), {
            "id": sublocation_id,
            "space_id": space.id,
            "naam": normalized_name,
            "active": True,
        })
        return ProvisionedSublocation(
            id=sublocation_id,
            name=normalized_name,
            space_id=space.id,
            space_name=space.name,
        )

    sublocation_id = str(uuid.uuid4())
    conn.execute(text("""
        INSERT INTO sublocations (id, naam, space_id, active)
        VALUES (:id, :naam, :space_id, :active)
    """), {
        "id": sublocation_id,
        "naam": normalized_name,
        "space_id": space.id,
        "active": True,
    })
    return ProvisionedSublocation(
        id=sublocation_id,
        name=normalized_name,
        space_id=space.id,
        space_name=space.name,
    )


def provision_waar_inhuis_locations(
    conn,
    *,
    household_id: str,
    main_locations: list[str],
    sublocations: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    normalized_main_locations: list[str] = []
    seen_main: set[str] = set()
    for raw_name in main_locations:
        normalized_name = _normalize_name(raw_name, label="Hoofdlocatie")
        key = normalized_name.casefold()
        if key in seen_main:
            raise ValueError(f"Hoofdlocatie '{normalized_name}' is dubbel gekozen")
        seen_main.add(key)
        normalized_main_locations.append(normalized_name)

    if not normalized_main_locations:
        raise ValueError("Kies minimaal één hoofdlocatie")
    if len(normalized_main_locations) > 12:
        raise ValueError("Kies maximaal 12 hoofdlocaties tijdens onboarding")
    if len(sublocations) > 30:
        raise ValueError("Voeg maximaal 30 sublocaties toe tijdens onboarding")

    ensure_location_foundation(conn)
    spaces_by_key: dict[str, ProvisionedSpace] = {}
    provisioned_spaces: list[ProvisionedSpace] = []
    for name in normalized_main_locations:
        space = _resolve_or_create_space(
            conn,
            household_id=normalized_household_id,
            name=name,
        )
        spaces_by_key[name.casefold()] = space
        provisioned_spaces.append(space)

    provisioned_sublocations: list[ProvisionedSublocation] = []
    seen_sublocations: set[tuple[str, str]] = set()
    for item in sublocations:
        raw_space_name = item.get("space_name")
        raw_name = item.get("name")
        space_name = _normalize_name(raw_space_name, label="Hoofdlocatie bij sublocatie")
        sublocation_name = _normalize_name(raw_name, label="Sublocatie")
        space = spaces_by_key.get(space_name.casefold())
        if not space:
            raise ValueError(
                f"Sublocatie '{sublocation_name}' verwijst naar een niet-gekozen hoofdlocatie"
            )
        duplicate_key = (space.name.casefold(), sublocation_name.casefold())
        if duplicate_key in seen_sublocations:
            raise ValueError(
                f"Sublocatie '{sublocation_name}' is dubbel gekozen onder '{space.name}'"
            )
        seen_sublocations.add(duplicate_key)
        provisioned_sublocations.append(
            _resolve_or_create_sublocation(
                conn,
                space=space,
                name=sublocation_name,
            )
        )

    return {
        "spaces": [
            {"id": space.id, "name": space.name}
            for space in provisioned_spaces
        ],
        "sublocations": [
            {
                "id": sublocation.id,
                "name": sublocation.name,
                "space_id": sublocation.space_id,
                "space_name": sublocation.space_name,
            }
            for sublocation in provisioned_sublocations
        ],
    }


def provision_waar_inhuis_expansion_locations(
    conn,
    *,
    household_id: str,
    main_locations: list[str],
    sublocations: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Add only missing location detail while preserving every existing location."""
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    if len(main_locations) > 12:
        raise ValueError("Voeg maximaal 12 nieuwe hoofdlocaties tegelijk toe")
    if len(sublocations) > 30:
        raise ValueError("Voeg maximaal 30 nieuwe sublocaties tegelijk toe")

    ensure_location_foundation(conn)
    existing_rows = conn.execute(text("""
        SELECT id, naam
        FROM spaces
        WHERE household_id = :household_id
          AND COALESCE(active, :active) = :active
        ORDER BY lower(trim(naam)), id
    """), {
        "household_id": normalized_household_id,
        "active": True,
    }).mappings().all()

    spaces_by_key: dict[str, ProvisionedSpace] = {
        _normalize_name(row.get("naam"), label="Hoofdlocatie").casefold(): ProvisionedSpace(
            id=str(row.get("id") or "").strip(),
            name=_normalize_name(row.get("naam"), label="Hoofdlocatie"),
        )
        for row in existing_rows
    }

    added_spaces: list[ProvisionedSpace] = []
    seen_new: set[str] = set()
    for raw_name in main_locations:
        normalized_name = _normalize_name(raw_name, label="Hoofdlocatie")
        key = normalized_name.casefold()
        if key in seen_new:
            raise ValueError(f"Hoofdlocatie '{normalized_name}' is dubbel gekozen")
        seen_new.add(key)
        if key in spaces_by_key:
            continue
        space = _resolve_or_create_space(
            conn,
            household_id=normalized_household_id,
            name=normalized_name,
        )
        spaces_by_key[key] = space
        added_spaces.append(space)

    if not spaces_by_key:
        raise ValueError("Kies minimaal één hoofdlocatie om Waar Inhuis toe te voegen")

    added_sublocations: list[ProvisionedSublocation] = []
    seen_sublocations: set[tuple[str, str]] = set()
    for item in sublocations:
        space_name = _normalize_name(item.get("space_name"), label="Hoofdlocatie bij sublocatie")
        sublocation_name = _normalize_name(item.get("name"), label="Sublocatie")
        space = spaces_by_key.get(space_name.casefold())
        if not space:
            raise ValueError(
                f"Sublocatie '{sublocation_name}' verwijst naar een onbekende hoofdlocatie"
            )
        duplicate_key = (space.name.casefold(), sublocation_name.casefold())
        if duplicate_key in seen_sublocations:
            raise ValueError(
                f"Sublocatie '{sublocation_name}' is dubbel gekozen onder '{space.name}'"
            )
        seen_sublocations.add(duplicate_key)
        added_sublocations.append(
            _resolve_or_create_sublocation(conn, space=space, name=sublocation_name)
        )

    return {
        "spaces": [{"id": item.id, "name": item.name} for item in added_spaces],
        "sublocations": [
            {
                "id": item.id,
                "name": item.name,
                "space_id": item.space_id,
                "space_name": item.space_name,
            }
            for item in added_sublocations
        ],
    }