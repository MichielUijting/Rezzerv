import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_PERSONAL_HOUSEHOLD_NAME,
    ensure_frontteam_household_for_session_runtime,
    resolve_frontteam_personal_household_id,
)
from app.services.server_session_service import (
    create_server_session,
    create_system_server_session,
    public_session_payload,
    resolve_server_session,
)


def build_connection():
    engine = create_engine("sqlite:///:memory:")
    conn = engine.connect()
    conn.execute(text("""
        CREATE TABLE household_registry (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            context_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        INSERT INTO household_registry(id, naam, context_type)
        VALUES
          ('1', 'Normaal huishouden', 'regular'),
          ('frontteam', 'Historisch Frontteam', 'regular')
    """))
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE
        )
    """))
    conn.execute(text("""
        CREATE TABLE household_memberships (
            user_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, household_id)
        )
    """))
    ensure_authorization_foundation(conn)
    conn.execute(text("""
        INSERT INTO app_users(id, email)
        VALUES
          ('front-a', 'front-a@example.test'),
          ('front-b', 'front-b@example.test'),
          ('front-inactive', 'front-inactive@example.test'),
          ('regular-admin', 'regular-admin@example.test')
    """))
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES
          ('front-a', 'platform.frontteam', 1),
          ('front-b', 'platform.frontteam', 1),
          ('front-inactive', 'platform.frontteam', 0)
    """))
    conn.execute(text("""
        INSERT INTO household_memberships(user_id, household_id, role)
        VALUES
          ('front-a', '1', 'admin'),
          ('front-a', 'frontteam', 'admin'),
          ('front-b', 'frontteam', 'admin'),
          ('regular-admin', 'frontteam', 'admin')
    """))
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
        VALUES
          ('1', 'front-a', 'household.admin'),
          ('frontteam', 'front-a', 'household.admin'),
          ('frontteam', 'front-b', 'household.admin'),
          ('frontteam', 'regular-admin', 'household.admin')
    """))
    conn.commit()
    return engine, conn


def test_frontteam_provisioning_creates_one_distinct_regular_household_per_active_user():
    engine, conn = build_connection()
    try:
        result = ensure_frontteam_household_for_session_runtime(conn)
        household_a = resolve_frontteam_personal_household_id(conn, "front-a")
        household_b = resolve_frontteam_personal_household_id(conn, "front-b")

        assert result.active_frontteam_users == 2
        assert result.households_created == 2
        assert result.memberships_created == 2
        assert result.legacy_memberships_removed == 2
        assert household_a
        assert household_b
        assert household_a != household_b
        assert set(result.personal_household_ids) == {household_a, household_b}
        assert resolve_frontteam_personal_household_id(conn, "front-inactive") is None

        mappings = conn.execute(text("""
            SELECT user_id, household_id
            FROM frontteam_personal_households
            ORDER BY user_id
        """)).mappings().all()
        assert [(row["user_id"], row["household_id"]) for row in mappings] == [
            ("front-a", household_a),
            ("front-b", household_b),
        ]

        households = conn.execute(text("""
            SELECT id, naam, context_type
            FROM household_registry
            WHERE id IN (:a, :b)
            ORDER BY id
        """), {"a": household_a, "b": household_b}).mappings().all()
        assert len(households) == 2
        assert {row["naam"] for row in households} == {FRONTTEAM_PERSONAL_HOUSEHOLD_NAME}
        assert {row["context_type"] for row in households} == {"regular"}

        memberships = conn.execute(text("""
            SELECT hm.user_id, hm.household_id, hm.role, mr.role_key, mr.active
            FROM household_memberships hm
            JOIN auth_membership_roles mr
              ON mr.household_id = hm.household_id
             AND mr.membership_id = hm.user_id
            WHERE hm.user_id IN ('front-a', 'front-b')
              AND hm.household_id IN (:a, :b)
            ORDER BY hm.user_id
        """), {"a": household_a, "b": household_b}).mappings().all()
        assert len(memberships) == 2
        assert {(row["user_id"], row["household_id"]) for row in memberships} == {
            ("front-a", household_a),
            ("front-b", household_b),
        }
        assert {row["role"] for row in memberships} == {"admin"}
        assert {row["role_key"] for row in memberships} == {"household.admin"}
        assert {row["active"] for row in memberships} == {1}

        # The historical shared household is retained as data, but active
        # Frontteam memberships are removed from it. Unrelated memberships and
        # other ordinary household memberships are preserved.
        assert conn.execute(text("""
            SELECT COUNT(*) FROM household_registry WHERE id = :id
        """), {"id": FRONTTEAM_HOUSEHOLD_ID}).scalar_one() == 1
        assert conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE household_id = :id AND user_id IN ('front-a', 'front-b')
        """), {"id": FRONTTEAM_HOUSEHOLD_ID}).scalar_one() == 0
        assert conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE household_id = :id AND user_id = 'regular-admin'
        """), {"id": FRONTTEAM_HOUSEHOLD_ID}).scalar_one() == 1
        assert conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE household_id = '1' AND user_id = 'front-a'
        """)).scalar_one() == 1
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_personal_provisioning_is_idempotent():
    engine, conn = build_connection()
    try:
        first = ensure_frontteam_household_for_session_runtime(conn)
        second = ensure_frontteam_household_for_session_runtime(conn)

        assert first.households_created == 2
        assert first.memberships_created == 2
        assert second.households_created == 0
        assert second.memberships_created == 0
        assert second.memberships_updated == 2
        assert first.personal_household_ids == second.personal_household_ids
        assert conn.execute(text("SELECT COUNT(*) FROM frontteam_personal_households")).scalar_one() == 2
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_regular_session_uses_own_personal_household_and_platform_permissions():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        household_a = resolve_frontteam_personal_household_id(conn, "front-a")
        raw_session_id, created = create_server_session(
            conn,
            user_id="front-a",
            active_household_id=household_a,
        )
        resolved = resolve_server_session(conn, raw_session_id)
        payload = public_session_payload(resolved)

        assert created.context_type == resolved.context_type == "regular"
        assert created.active_household_id == resolved.active_household_id == household_a
        assert created.role == resolved.role == "admin"
        assert created.is_frontteam is resolved.is_frontteam is True
        assert payload["is_frontteam"] is True
        assert payload["is_platform_superuser"] is False
        for permission in (
            "platform.external_products.view",
            "platform.external_products.search",
            "platform.external_products.link_existing",
        ):
            assert payload["permissions"][permission] is True
        assert "platform_roles" not in payload
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_session_fails_closed_immediately_after_platform_role_revocation():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        household_a = resolve_frontteam_personal_household_id(conn, "front-a")
        raw_session_id, _ = create_server_session(
            conn,
            user_id="front-a",
            active_household_id=household_a,
        )
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'front-a' AND role_key = 'platform.frontteam'
        """))

        with pytest.raises(HTTPException) as exc:
            resolve_server_session(conn, raw_session_id)

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()


def test_active_frontteam_role_cannot_select_unrelated_or_other_frontteam_household():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        household_b = resolve_frontteam_personal_household_id(conn, "front-b")

        for forbidden_household_id in ("1", household_b, FRONTTEAM_HOUSEHOLD_ID):
            with pytest.raises(HTTPException) as exc:
                create_server_session(
                    conn,
                    user_id="front-a",
                    active_household_id=forbidden_household_id,
                )
            assert exc.value.status_code == 403
    finally:
        conn.close()
        engine.dispose()


def test_legacy_shared_frontteam_household_never_grants_runtime_authority():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        with pytest.raises(HTTPException) as exc:
            create_server_session(
                conn,
                user_id="regular-admin",
                active_household_id=FRONTTEAM_HOUSEHOLD_ID,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.parametrize(
    "system_role",
    [
        "platform.superuser",
        "platform.ip_owner",
    ],
)
def test_frontteam_system_role_conflict_fails_closed_in_session_service(system_role):
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('0', 'Systeemhuishouden', 'system')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('front-a', :role_key, 1)
        """), {"role_key": system_role})

        with pytest.raises(HTTPException) as exc:
            create_system_server_session(
                conn,
                user_id="front-a",
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()
