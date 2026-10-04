from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

AGE_BANDS = frozenset({"0_3", "4_12", "13_17", "18_34", "35_49", "50_64", "65_79", "80_plus"})
RESIDENT_TYPES = frozenset({"adult", "child", "other"})


def _clean(value: object, max_length: int) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"Waarde mag maximaal {max_length} tekens bevatten")
    return normalized


def _stores(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = _clean(raw, 80)
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) > 10:
            raise ValueError("Maximaal 10 voorkeurswinkels")
    return result


def _household_name(conn: Connection, household_id: str) -> str:
    row = conn.execute(text("""
        SELECT naam FROM household_registry
        WHERE CAST(id AS TEXT) = :household_id
        LIMIT 1
    """), {"household_id": household_id}).mappings().first()
    if not row:
        raise LookupError("Huishouden niet gevonden")
    return str(row.get("naam") or "Mijn huishouden")


def _profile_row(conn: Connection, household_id: str) -> dict:
    row = conn.execute(text("""
        SELECT household_id, street, house_number, house_number_addition,
               postal_code, city, country_code, preferred_stores_json,
               shopping_interval_days, default_reserve_days
        FROM household_profiles
        WHERE household_id = :household_id
        LIMIT 1
    """), {"household_id": household_id}).mappings().first()
    if not row:
        return {
            "household_id": household_id,
            "street": None,
            "house_number": None,
            "house_number_addition": None,
            "postal_code": None,
            "city": None,
            "country_code": "NL",
            "preferred_stores_json": "[]",
            "shopping_interval_days": None,
            "default_reserve_days": None,
        }
    return dict(row)


def _linked_users(conn: Connection, household_id: str) -> list[dict]:
    inspector = inspect(conn)
    membership_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("household_memberships")
    }
    user_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("app_users")
    }
    if "household_id" not in membership_columns or "id" not in user_columns or "email" not in user_columns:
        return []

    join_parts: list[str] = []
    if "user_id" in membership_columns:
        join_parts.append("CAST(hm.user_id AS TEXT) = CAST(u.id AS TEXT)")
    if "user_email" in membership_columns:
        join_parts.append("lower(trim(hm.user_email)) = lower(trim(u.email))")
    if not join_parts:
        return []

    active_condition = (
        "lower(trim(COALESCE(hm.status, 'active'))) = 'active'"
        if "status" in membership_columns
        else "1 = 1"
    )
    display_name_expression = "u.display_name" if "display_name" in user_columns else "NULL"
    rows = conn.execute(text(f"""
        SELECT DISTINCT u.id AS user_id, u.email, {display_name_expression} AS display_name
        FROM household_memberships hm
        JOIN app_users u ON ({' OR '.join(join_parts)})
        WHERE CAST(hm.household_id AS TEXT) = :household_id
          AND {active_condition}
        ORDER BY lower(trim(u.email))
    """), {"household_id": household_id}).mappings().all()
    return [
        {
            "user_id": str(row["user_id"]),
            "email": str(row.get("email") or ""),
            "display_name": str(row.get("display_name") or "").strip(),
        }
        for row in rows
    ]


def _residents(conn: Connection, household_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT id, first_name, last_name, resident_type, birth_date, age_band, linked_user_id
        FROM household_residents
        WHERE household_id = :household_id
        ORDER BY lower(first_name), lower(COALESCE(last_name, '')), id
    """), {"household_id": household_id}).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "first_name": str(row.get("first_name") or ""),
            "last_name": str(row.get("last_name") or ""),
            "resident_type": str(row.get("resident_type") or "other"),
            "birth_date": row.get("birth_date").isoformat() if row.get("birth_date") else None,
            "age_band": row.get("age_band"),
            "linked_user_id": str(row.get("linked_user_id")) if row.get("linked_user_id") else None,
        }
        for row in rows
    ]


def public_household_profile(conn: Connection, household_id: str, *, can_manage: bool) -> dict:
    profile = _profile_row(conn, household_id)
    residents = _residents(conn, household_id)
    try:
        stores = json.loads(str(profile.get("preferred_stores_json") or "[]"))
    except json.JSONDecodeError:
        stores = []
    if not isinstance(stores, list):
        stores = []
    return {
        "household_id": household_id,
        "household_name": _household_name(conn, household_id),
        "street": profile.get("street"),
        "house_number": profile.get("house_number"),
        "house_number_addition": profile.get("house_number_addition"),
        "postal_code": profile.get("postal_code"),
        "city": profile.get("city"),
        "country_code": profile.get("country_code") or "NL",
        "preferred_stores": [str(item) for item in stores if str(item).strip()],
        "shopping_interval_days": profile.get("shopping_interval_days"),
        "default_reserve_days": profile.get("default_reserve_days"),
        "resident_count": len(residents),
        "residents": residents,
        "linked_users": _linked_users(conn, household_id),
        "can_manage": bool(can_manage),
    }


def save_household_profile(
    conn: Connection,
    household_id: str,
    *,
    household_name: str,
    street: str | None,
    house_number: str | None,
    house_number_addition: str | None,
    postal_code: str | None,
    city: str | None,
    country_code: str | None,
    preferred_stores: list[str] | None,
    shopping_interval_days: int | None,
    default_reserve_days: int | None,
) -> None:
    name = _clean(household_name, 120)
    if not name:
        raise ValueError("Naam huishouden is verplicht")
    if shopping_interval_days is not None and not 1 <= int(shopping_interval_days) <= 90:
        raise ValueError("Boodschappeninterval moet tussen 1 en 90 dagen liggen")
    if default_reserve_days is not None and not 0 <= int(default_reserve_days) <= 90:
        raise ValueError("Reservevoorraad moet tussen 0 en 90 dagen liggen")
    country = (_clean(country_code, 2) or "NL").upper()
    if len(country) != 2:
        raise ValueError("Landcode moet uit 2 letters bestaan")

    updated = conn.execute(text("""
        UPDATE household_registry
        SET naam = :name
        WHERE CAST(id AS TEXT) = :household_id
    """), {"name": name, "household_id": household_id})
    if int(updated.rowcount or 0) != 1:
        raise LookupError("Huishouden niet gevonden")

    conn.execute(text("""
        INSERT INTO household_profiles(
            household_id, street, house_number, house_number_addition,
            postal_code, city, country_code, preferred_stores_json,
            shopping_interval_days, default_reserve_days, updated_at
        )
        VALUES(
            :household_id, :street, :house_number, :house_number_addition,
            :postal_code, :city, :country_code, :preferred_stores_json,
            :shopping_interval_days, :default_reserve_days, :updated_at
        )
        ON CONFLICT(household_id) DO UPDATE SET
            street = excluded.street,
            house_number = excluded.house_number,
            house_number_addition = excluded.house_number_addition,
            postal_code = excluded.postal_code,
            city = excluded.city,
            country_code = excluded.country_code,
            preferred_stores_json = excluded.preferred_stores_json,
            shopping_interval_days = excluded.shopping_interval_days,
            default_reserve_days = excluded.default_reserve_days,
            updated_at = excluded.updated_at
    """), {
        "household_id": household_id,
        "street": _clean(street, 120),
        "house_number": _clean(house_number, 20),
        "house_number_addition": _clean(house_number_addition, 20),
        "postal_code": _clean(postal_code, 20),
        "city": _clean(city, 120),
        "country_code": country,
        "preferred_stores_json": json.dumps(_stores(preferred_stores), ensure_ascii=False),
        "shopping_interval_days": int(shopping_interval_days) if shopping_interval_days is not None else None,
        "default_reserve_days": int(default_reserve_days) if default_reserve_days is not None else None,
        "updated_at": datetime.now(timezone.utc),
    })


def _validate_resident(
    *,
    first_name: str,
    last_name: str | None,
    resident_type: str,
    birth_date: date | None,
    age_band: str | None,
) -> tuple[str, str | None, str, date | None, str | None]:
    first = _clean(first_name, 80)
    if not first:
        raise ValueError("Voornaam is verplicht")
    last = _clean(last_name, 120)
    rtype = str(resident_type or "").strip().lower()
    if rtype not in RESIDENT_TYPES:
        raise ValueError("Kies volwassene, kind of anders")
    band = str(age_band or "").strip() or None
    if band is not None and band not in AGE_BANDS:
        raise ValueError("Ongeldige leeftijdscategorie")
    if birth_date is not None:
        today = date.today()
        if birth_date > today:
            raise ValueError("Geboortedatum kan niet in de toekomst liggen")
        if birth_date.year < today.year - 130:
            raise ValueError("Geboortedatum ligt te ver in het verleden")
    return first, last, rtype, birth_date, band


def _validate_linked_user(conn: Connection, household_id: str, linked_user_id: str | None) -> str | None:
    user_id = str(linked_user_id or "").strip() or None
    if not user_id:
        return None
    allowed = {item["user_id"] for item in _linked_users(conn, household_id)}
    if user_id not in allowed:
        raise ValueError("Gekoppelde gebruiker hoort niet bij dit huishouden")
    return user_id


def create_resident(conn: Connection, household_id: str, **payload) -> str:
    first, last, rtype, birth_date, band = _validate_resident(
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        resident_type=payload.get("resident_type"),
        birth_date=payload.get("birth_date"),
        age_band=payload.get("age_band"),
    )
    resident_id = str(uuid.uuid4())
    linked_user_id = _validate_linked_user(conn, household_id, payload.get("linked_user_id"))
    conn.execute(text("""
        INSERT INTO household_residents(
            id, household_id, first_name, last_name, resident_type,
            birth_date, age_band, linked_user_id
        )
        VALUES(
            :id, :household_id, :first_name, :last_name, :resident_type,
            :birth_date, :age_band, :linked_user_id
        )
    """), {
        "id": resident_id,
        "household_id": household_id,
        "first_name": first,
        "last_name": last,
        "resident_type": rtype,
        "birth_date": birth_date,
        "age_band": band,
        "linked_user_id": linked_user_id,
    })
    return resident_id


def update_resident(conn: Connection, household_id: str, resident_id: str, **payload) -> None:
    first, last, rtype, birth_date, band = _validate_resident(
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        resident_type=payload.get("resident_type"),
        birth_date=payload.get("birth_date"),
        age_band=payload.get("age_band"),
    )
    linked_user_id = _validate_linked_user(conn, household_id, payload.get("linked_user_id"))
    result = conn.execute(text("""
        UPDATE household_residents
        SET first_name = :first_name,
            last_name = :last_name,
            resident_type = :resident_type,
            birth_date = :birth_date,
            age_band = :age_band,
            linked_user_id = :linked_user_id,
            updated_at = :updated_at
        WHERE id = :id AND household_id = :household_id
    """), {
        "id": resident_id,
        "household_id": household_id,
        "first_name": first,
        "last_name": last,
        "resident_type": rtype,
        "birth_date": birth_date,
        "age_band": band,
        "linked_user_id": linked_user_id,
        "updated_at": datetime.now(timezone.utc),
    })
    if int(result.rowcount or 0) != 1:
        raise LookupError("Bewoner niet gevonden")


def delete_resident(conn: Connection, household_id: str, resident_id: str) -> None:
    result = conn.execute(text("""
        DELETE FROM household_residents
        WHERE id = :id AND household_id = :household_id
    """), {"id": resident_id, "household_id": household_id})
    if int(result.rowcount or 0) != 1:
        raise LookupError("Bewoner niet gevonden")
