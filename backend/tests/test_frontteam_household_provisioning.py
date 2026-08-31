import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_PERSONAL_HOUSEHOLD_NAME,
    ensure_frontteam_household_for_session_runtime,
    resolve_frontteam_personal_household_id,
)
from app.services.server_session_service import (
    create_server_session,
    public_session_payload,
    resolve_server_session,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
    seed_membership,
    seed_user,
)


def _membership_columns(conn):
    return {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_memberships")
    }


def _membership_rows(conn, *, user_id: str, email: str):
    columns = _membership_columns(conn)
    id_column = "id" if "id" in columns else "membership_id" if "membership_id" in columns else None
    role_column = "role" if "role" in columns else "rol"
    predicates = []
    params = {"user_id": user_id, "email": email}
    if "user_id" in columns:
        predicates.append("CAST(user_id AS TEXT) = :user_id")
    if "user_email" in columns:
        predicates.append("lower(trim(user_email)) = lower(trim(:email))")
    elif "email" in columns:
        predicates.append("lower(trim(email)) = lower(trim(:email))")
    if not predicates:
        raise RuntimeError("household_memberships mist gebruikersidentiteit")
    id_sql = f"CAST({id_column} AS TEXT)" if id_column else "NULL"
    return conn.execute(
        text(
            f"SELECT {id_sql} AS membership_id, CAST(household_id AS TEXT) AS household_id, "
            f"{role_column} AS role FROM household_memberships "
            f"WHERE {' OR '.join(predicates)} ORDER BY household_id"
        ),
        params,
    ).mappings().all()


def _seed_frontteam_fixture():
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id="1", name="Normaal huishouden")
        seed_household(
            conn,
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            name="Historisch Frontteam",
        )
        for user_id, email in (
            ("front-a", "front-a@example.test"),
            ("front-b", "front-b@example.test"),
            ("front-inactive", "front-inactive@example.test"),
            ("regular-admin", "regular-admin@example.test"),
        ):
            seed_user(conn, user_id=user_id, email=email, password="FrontteamTest123!")
        seed_membership(
            conn,
            membership_id="front-a-normal",
            household_id="1",
            user_id="front-a",
            email="front-a@example.test",
            role="admin",
        )
        seed_membership(
            conn,
            membership_id="front-a-legacy",
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            user_id="front-a",
            email="front-a@example.test",
            role="admin",
        )
        seed_membership(
            conn,
            membership_id="front-b-legacy",
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            user_id="front-b",
            email="front-b@example.test",
            role="admin",
        )
        seed_membership(
            conn,
            membership_id="regular-admin-legacy",
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            user_id="regular-admin",
            email="regular-admin@example.test",
            role="admin",
        )
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('front-a', 'platform.frontteam', TRUE),
              ('front-b', 'platform.frontteam', TRUE),
              ('front-inactive', 'platform.frontteam', FALSE)
        """))
    return engine


def test_frontteam_provisioning_creates_one_distinct_regular_household_per_active_user():
    engine = _seed_frontteam_fixture()
    try:
        with engine.begin() as conn:
            result = ensure_frontteam_household_for_session_runtime(conn)
            household_a = resolve_frontteam_personal_household_id(conn, "front-a")
            household_b = resolve_frontteam_personal_household_id(conn, "front-b")

            assert result.active_frontteam_users == 2
            assert result.households_created == 2
            assert result.memberships_created == 2
            assert result.legacy_memberships_removed == 2
            assert household_a and household_b and household_a != household_b
            assert set(result.personal_household_ids) == {household_a, household_b}
            assert resolve_frontteam_personal_household_id(conn, "front-inactive") is None

            households = conn.execute(text("""
                SELECT id, naam, context_type
                FROM household_registry
                WHERE id IN (:a, :b)
                ORDER BY id
            """), {"a": household_a, "b": household_b}).mappings().all()
            assert len(households) == 2
            assert {row["naam"] for row in households} == {FRONTTEAM_PERSONAL_HOUSEHOLD_NAME}
            assert {row["context_type"] for row in households} == {"regular"}

            rows_a = _membership_rows(
                conn,
                user_id="front-a",
                email="front-a@example.test",
            )
            rows_b = _membership_rows(
                conn,
                user_id="front-b",
                email="front-b@example.test",
            )
            assert household_a in {row["household_id"] for row in rows_a}
            assert household_b in {row["household_id"] for row in rows_b}
            assert FRONTTEAM_HOUSEHOLD_ID not in {row["household_id"] for row in rows_a}
            assert FRONTTEAM_HOUSEHOLD_ID not in {row["household_id"] for row in rows_b}
            assert "1" in {row["household_id"] for row in rows_a}

            regular_rows = _membership_rows(
                conn,
                user_id="regular-admin",
                email="regular-admin@example.test",
            )
            assert FRONTTEAM_HOUSEHOLD_ID in {
                row["household_id"] for row in regular_rows
            }
    finally:
        engine.dispose()


def test_frontteam_personal_provisioning_is_idempotent():
    engine = _seed_frontteam_fixture()
    try:
        with engine.begin() as conn:
            first = ensure_frontteam_household_for_session_runtime(conn)
            second = ensure_frontteam_household_for_session_runtime(conn)
            assert first.active_frontteam_users == second.active_frontteam_users == 2
            assert second.households_created == 0
            assert second.memberships_created == 0
            assert second.legacy_memberships_removed == 0
            assert second.personal_household_ids == first.personal_household_ids
    finally:
        engine.dispose()


def test_frontteam_personal_household_supports_regular_server_session():
    engine = _seed_frontteam_fixture()
    try:
        with engine.begin() as conn:
            ensure_frontteam_household_for_session_runtime(conn)
            household_id = resolve_frontteam_personal_household_id(conn, "front-a")
            assert household_id
            raw_session, created = create_server_session(
                conn,
                user_id="front-a",
                active_household_id=household_id,
            )
            resolved = resolve_server_session(conn, raw_session)
            payload = public_session_payload(resolved)

            assert created.context_type == resolved.context_type == "regular"
            assert created.active_household_id == resolved.active_household_id == household_id
            assert created.role == resolved.role == "admin"
            assert resolved.is_frontteam is True
            assert payload["is_frontteam"] is True
    finally:
        engine.dispose()


def test_inactive_frontteam_user_cannot_gain_personal_household_or_frontteam_session():
    engine = _seed_frontteam_fixture()
    try:
        with engine.begin() as conn:
            ensure_frontteam_household_for_session_runtime(conn)
            assert resolve_frontteam_personal_household_id(conn, "front-inactive") is None
            with pytest.raises(HTTPException):
                create_server_session(
                    conn,
                    user_id="front-inactive",
                    active_household_id=FRONTTEAM_HOUSEHOLD_ID,
                )
    finally:
        engine.dispose()
