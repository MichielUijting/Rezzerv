from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from app.services.household_profile_service import (
    create_resident,
    public_household_profile,
    save_household_profile,
    update_resident,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                display_name TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_profiles (
                household_id TEXT PRIMARY KEY,
                street TEXT,
                house_number TEXT,
                house_number_addition TEXT,
                postal_code TEXT,
                city TEXT,
                country_code TEXT,
                preferred_stores_json TEXT NOT NULL DEFAULT '[]',
                shopping_interval_days INTEGER,
                default_reserve_days INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_residents (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT,
                resident_type TEXT NOT NULL,
                birth_date DATE,
                age_band TEXT,
                linked_user_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX uq_household_resident_linked_user
            ON household_residents(household_id, linked_user_id)
            WHERE linked_user_id IS NOT NULL
        """))
        conn.execute(text("INSERT INTO household_registry(id, naam) VALUES ('h1', 'Mijn huishouden')"))
        conn.execute(text("INSERT INTO app_users(id, email, display_name) VALUES ('u1', 'een@example.test', 'Een')"))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_id, user_email, status)
            VALUES ('m1', 'h1', 'u1', 'een@example.test', 'active')
        """))
    return engine


def test_household_profile_separates_residents_from_app_accounts():
    engine = _engine()
    with engine.begin() as conn:
        initial = public_household_profile(conn, "h1", can_manage=True)
        assert initial["resident_count"] == 0
        assert len(initial["linked_users"]) == 1

        save_household_profile(
            conn,
            "h1",
            household_name="Gezin Test",
            street="Dorpsstraat",
            house_number="12",
            house_number_addition="A",
            postal_code="1234 AB",
            city="Testdam",
            country_code="nl",
            preferred_stores=["Winkel A", "Winkel B", "Winkel A"],
            shopping_interval_days=7,
            default_reserve_days=5,
        )
        create_resident(
            conn,
            "h1",
            first_name="Alex",
            last_name="Test",
            resident_type="adult",
            birth_date=date(1980, 1, 2),
            age_band=None,
            linked_user_id="u1",
        )
        create_resident(
            conn,
            "h1",
            first_name="Sam",
            last_name=None,
            resident_type="child",
            birth_date=None,
            age_band="4_12",
            linked_user_id=None,
        )

        payload = public_household_profile(conn, "h1", can_manage=True)
        assert payload["household_name"] == "Gezin Test"
        assert payload["resident_count"] == 2
        assert payload["preferred_stores"] == ["Winkel A", "Winkel B"]
        assert payload["shopping_interval_days"] == 7
        assert payload["default_reserve_days"] == 5
        assert {item["first_name"] for item in payload["residents"]} == {"Alex", "Sam"}
        assert sum(1 for item in payload["residents"] if item["linked_user_id"]) == 1


def test_resident_link_must_belong_to_same_household():
    engine = _engine()
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="hoort niet bij dit huishouden"):
            create_resident(
                conn,
                "h1",
                first_name="Onbekend",
                last_name=None,
                resident_type="adult",
                birth_date=None,
                age_band="18_34",
                linked_user_id="u-other",
            )


def test_resident_update_keeps_household_scope():
    engine = _engine()
    with engine.begin() as conn:
        resident_id = create_resident(
            conn,
            "h1",
            first_name="Alex",
            last_name=None,
            resident_type="adult",
            birth_date=None,
            age_band="35_49",
            linked_user_id=None,
        )
        update_resident(
            conn,
            "h1",
            resident_id,
            first_name="Alexandra",
            last_name=None,
            resident_type="adult",
            birth_date=None,
            age_band="35_49",
            linked_user_id=None,
        )
        payload = public_household_profile(conn, "h1", can_manage=False)
        assert payload["can_manage"] is False
        assert payload["residents"][0]["first_name"] == "Alexandra"
