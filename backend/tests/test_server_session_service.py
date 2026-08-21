from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from app.services.authorization_foundation_service import (
    ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.server_session_service import (
    create_none_server_session,
    create_server_session,
    ensure_server_session_schema,
    hash_session_id,
    public_session_payload,
    resolve_session_context_type,
    resolve_server_session,
    revoke_server_session,
    rotate_active_household,
)


@pytest.fixture()
def connection():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id VARCHAR(64) PRIMARY KEY,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, context_type)
            VALUES ('0', 'system'), ('1', 'regular'), ('2', 'regular')
        """))
        conn.execute(text("CREATE TABLE app_users (id VARCHAR(64) PRIMARY KEY, email VARCHAR(255) NOT NULL)"))
        conn.execute(
            text(
                """
                CREATE TABLE household_memberships (
                    user_id VARCHAR(64) NOT NULL,
                    household_id VARCHAR(64) NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    PRIMARY KEY (user_id, household_id)
                )
                """
            )
        )
        conn.execute(text("INSERT INTO app_users (id, email) VALUES ('u1', 'admin@rezzerv.local'), ('u2', 'lid@rezzerv.local')"))
        conn.execute(
            text(
                """
                INSERT INTO household_memberships (user_id, household_id, role)
                VALUES ('u1', '1', 'owner'), ('u1', '2', 'member'), ('u2', '2', 'member')
                """
            )
        )
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES
              ('1', 'u1', 'household.admin'),
              ('2', 'u1', 'household.member'),
              ('2', 'u2', 'household.member')
        """))
        yield conn


def assert_http_status(exc: pytest.ExceptionInfo[HTTPException], status_code: int):
    assert exc.value.status_code == status_code


def create_legacy_server_sessions_schema(conn):
    conn.execute(text("""
        CREATE TABLE server_sessions (
            id VARCHAR(64) PRIMARY KEY,
            session_token_hash VARCHAR(64) NOT NULL UNIQUE,
            user_id VARCHAR(64) NOT NULL,
            active_household_id VARCHAR(64) NOT NULL,
            issued_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            session_version INTEGER NOT NULL DEFAULT 1,
            revoked_at TIMESTAMP NULL,
            replaced_by_session_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE INDEX idx_server_sessions_user_active
        ON server_sessions(user_id, revoked_at, expires_at)
    """))


def legacy_server_sessions_sql() -> str:
    return """
        CREATE TABLE server_sessions (
            id VARCHAR(64) PRIMARY KEY,
            session_token_hash VARCHAR(64) NOT NULL UNIQUE,
            user_id VARCHAR(64) NOT NULL,
            active_household_id VARCHAR(64) NOT NULL,
            issued_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            session_version INTEGER NOT NULL DEFAULT 1,
            revoked_at TIMESTAMP NULL,
            replaced_by_session_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """


def assert_failed_upgrade_preserves_schema_and_data(conn):
    before_sql = conn.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one()
    before_rows = conn.execute(text("SELECT * FROM server_sessions")).all()

    with pytest.raises(RuntimeError):
        ensure_server_session_schema(conn)

    assert conn.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one() == before_sql
    assert conn.execute(text("SELECT * FROM server_sessions")).all() == before_rows
    assert inspect(conn).has_table("server_sessions__context_foundation") is False


def test_missing_session_fails_closed(connection):
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, None)
    assert_http_status(exc, 401)


def test_platform_admin_none_session_is_sql_null_and_resolves_without_membership(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('platform-admin', 'platform.platform_admin', 1)
    """))

    raw_session_id, created = create_none_server_session(
        connection,
        user_id='platform-admin',
    )
    resolved = resolve_server_session(connection, raw_session_id)
    stored_household_id = connection.execute(text("""
        SELECT active_household_id FROM server_sessions
        WHERE user_id = 'platform-admin'
    """)).scalar_one()

    assert stored_household_id is None
    assert created.active_household_id is resolved.active_household_id is None
    assert created.context_type == resolved.context_type == 'none'
    assert created.role is resolved.role is None
    assert public_session_payload(resolved) == {
        'user': {'id': 'platform-admin', 'email': 'platform@example.test'},
        'user_id': 'platform-admin',
        'email': 'platform@example.test',
        'active_household_id': None,
        'active_household_name': '',
        'role': None,
        'display_role': None,
        'permissions': {},
        'supported_permissions': [],
        'can_manage_member_permissions': False,
        'can_manage_members': False,
        'is_viewer': False,
        'is_platform_superuser': False,
        'is_frontteam': False,
        'session_version': 1,
        'expires_at': resolved.expires_at.isoformat(),
    }


def test_none_session_fails_closed_when_platform_admin_role_is_deactivated(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('platform-admin', 'platform.platform_admin', 1)
    """))
    raw_session_id, _ = create_none_server_session(connection, user_id='platform-admin')
    connection.execute(text("""
        UPDATE auth_platform_user_roles SET active = 0
        WHERE user_id = 'platform-admin' AND role_key = 'platform.platform_admin'
    """))

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_session_id)

    assert_http_status(exc, 403)


def test_none_session_creation_rejects_platform_admin_superuser_conflict(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES
          ('platform-admin', 'platform.platform_admin', 1),
          ('platform-admin', 'platform.superuser', 1)
    """))

    with pytest.raises(HTTPException) as exc:
        create_none_server_session(connection, user_id='platform-admin')

    assert_http_status(exc, 403)
    assert connection.execute(text(
        "SELECT COUNT(*) FROM server_sessions WHERE user_id = 'platform-admin'"
    )).scalar_one() == 0


def test_session_belongs_to_exactly_one_user_and_household(connection):
    raw_id, context = create_server_session(
        connection,
        user_id="u1",
        active_household_id="1",
    )

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.user_id == "u1"
    assert resolved.active_household_id == "1"
    assert resolved.role == "admin"
    assert resolved.context_type == "regular"
    assert context.session_id == resolved.session_id


def test_household_zero_is_never_a_fallback(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u1", active_household_id="0")
    assert_http_status(exc, 403)


def test_non_member_cannot_select_household(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u2", active_household_id="1")
    assert_http_status(exc, 403)


def test_stale_legacy_role_does_not_change_canonical_session_role(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE household_memberships SET role = 'member' WHERE user_id = 'u1' AND household_id = '1'")
    )

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.role == "admin"


def test_canonical_role_update_changes_session_role(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(text("""
        UPDATE auth_membership_roles SET role_key = 'household.member'
        WHERE household_id = '1' AND membership_id = 'u1'
    """))

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.role == "member"


def test_missing_role_never_escalates_to_superuser(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE auth_membership_roles SET active = 0 WHERE household_id = '1' AND membership_id = 'u1'")
    )

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id)
    assert_http_status(exc, 403)


def test_household_zero_keeps_temporary_v1_1_owner_session_compatibility(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('system-superuser', 'supergebruiker@rezzerv.local')
    """))
    connection.execute(text("""
        INSERT INTO household_memberships (user_id, household_id, role)
        VALUES ('system-superuser', '0', 'owner')
    """))
    connection.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
        VALUES ('0', 'system-superuser', 'household.admin')
    """))

    raw_id, created = create_server_session(
        connection,
        user_id='system-superuser',
        active_household_id='0',
    )
    resolved = resolve_server_session(connection, raw_id)
    payload = public_session_payload(resolved)

    assert created.role == 'owner'
    assert resolved.role == 'owner'
    assert created.context_type == resolved.context_type == 'system'
    assert connection.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = '0' AND membership_id = 'system-superuser'
    """)).scalar_one() == 'household.admin'
    assert connection.execute(text("""
        SELECT role FROM household_memberships
        WHERE household_id = '0' AND user_id = 'system-superuser'
    """)).scalar_one() == 'owner'
    granted = {key for key, allowed in payload['permissions'].items() if allowed}
    assert ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS <= granted
    assert not (V2_SUPERUSER_TARGET_PERMISSIONS - ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS) & granted


def test_revoked_session_returns_401(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    revoke_server_session(connection, raw_id)

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id)
    assert_http_status(exc, 401)


def test_expired_session_returns_401(connection):
    issued_at = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
    raw_id, _ = create_server_session(
        connection,
        user_id="u1",
        active_household_id="1",
        ttl=timedelta(minutes=5),
        now=issued_at,
    )

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id, now=issued_at + timedelta(minutes=6))
    assert_http_status(exc, 401)


def test_household_switch_rotates_and_invalidates_old_session(connection):
    raw_old, _ = create_server_session(connection, user_id="u1", active_household_id="1")

    raw_new, new_context = rotate_active_household(connection, raw_old, "2")

    assert raw_new != raw_old
    assert new_context.active_household_id == "2"
    assert resolve_server_session(connection, raw_new).active_household_id == "2"
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_old)
    assert_http_status(exc, 401)


def test_new_login_invalidates_existing_user_session(connection):
    raw_old, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    raw_new, _ = create_server_session(connection, user_id="u1", active_household_id="1")

    assert resolve_server_session(connection, raw_new).user_id == "u1"
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_old)
    assert_http_status(exc, 401)


def test_context_type_foundation_is_registry_authoritative(connection):
    assert resolve_session_context_type(connection, None) == "none"
    assert resolve_session_context_type(connection, "1") == "regular"
    assert resolve_session_context_type(connection, "0") == "system"


@pytest.mark.parametrize("household_id", ["missing", "", "demo-household"])
def test_context_type_foundation_never_falls_back(connection, household_id):
    with pytest.raises(HTTPException) as exc:
        resolve_session_context_type(connection, household_id)
    assert_http_status(exc, 403)


def test_context_type_foundation_rejects_unknown_registry_value(connection):
    connection.execute(text("""
        INSERT INTO household_registry(id, context_type)
        VALUES ('invalid', 'private')
    """))
    with pytest.raises(HTTPException) as exc:
        resolve_session_context_type(connection, "invalid")
    assert_http_status(exc, 403)


def test_session_schema_is_nullable_and_idempotent(connection):
    ensure_server_session_schema(connection)
    first_sql = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one()
    ensure_server_session_schema(connection)
    second_sql = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one()
    household_column = next(
        row for row in connection.exec_driver_sql("PRAGMA table_info(server_sessions)").mappings()
        if row["name"] == "active_household_id"
    )
    assert household_column["notnull"] == 0
    assert first_sql == second_sql


def test_legacy_session_schema_upgrade_preserves_every_value_and_constraint():
    engine = create_engine("sqlite:///:memory:")
    expected_rows = [
        (
            "active", "hash-active", "u1", "1",
            "2026-08-20 10:00:00", "2026-08-20 22:00:00", 1,
            None, None, "2026-08-20 10:00:00", "2026-08-20 10:00:00",
        ),
        (
            "revoked", "hash-revoked", "u2", "2",
            "2026-08-19 10:00:00", "2026-08-19 22:00:00", 4,
            "2026-08-19 11:00:00", "replacement",
            "2026-08-19 10:00:00", "2026-08-19 11:00:00",
        ),
    ]
    with engine.begin() as conn:
        create_legacy_server_sessions_schema(conn)
        conn.execute(text("""
            INSERT INTO server_sessions (
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at, session_version, revoked_at,
                replaced_by_session_id, created_at, updated_at
            ) VALUES (
                :id, :session_token_hash, :user_id, :active_household_id,
                :issued_at, :expires_at, :session_version, :revoked_at,
                :replaced_by_session_id, :created_at, :updated_at
            )
        """), [dict(zip(
            (
                "id", "session_token_hash", "user_id", "active_household_id",
                "issued_at", "expires_at", "session_version", "revoked_at",
                "replaced_by_session_id", "created_at", "updated_at",
            ), row
        )) for row in expected_rows])

        ensure_server_session_schema(conn)
        actual_rows = conn.execute(text("""
            SELECT id, session_token_hash, user_id, active_household_id,
                   issued_at, expires_at, session_version, revoked_at,
                   replaced_by_session_id, created_at, updated_at
            FROM server_sessions ORDER BY id
        """)).all()
        columns = {column["name"]: column for column in inspect(conn).get_columns("server_sessions")}
        indexes = {index["name"] for index in inspect(conn).get_indexes("server_sessions")}

        assert [tuple(row) for row in actual_rows] == sorted(expected_rows)
        assert columns["active_household_id"]["nullable"] is True
        assert columns["session_version"]["default"] == "1"
        assert columns["created_at"]["default"] == "CURRENT_TIMESTAMP"
        assert columns["updated_at"]["default"] == "CURRENT_TIMESTAMP"
        assert "idx_server_sessions_user_active" in indexes
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO server_sessions(
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at
                ) VALUES ('duplicate', 'hash-active', 'u3', NULL,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))


def test_existing_legacy_session_resolves_after_schema_upgrade(connection):
    connection.execute(text("DROP TABLE IF EXISTS server_sessions"))
    create_legacy_server_sessions_schema(connection)
    raw_session_id = "legacy-session-token"
    now = datetime.now(timezone.utc)
    connection.execute(text("""
        INSERT INTO server_sessions(
            id, session_token_hash, user_id, active_household_id,
            issued_at, expires_at, session_version, created_at, updated_at
        ) VALUES (
            'legacy-session', :token_hash, 'u1', '1',
            :issued_at, :expires_at, 3, :issued_at, :issued_at
        )
    """), {
        "token_hash": hash_session_id(raw_session_id),
        "issued_at": now,
        "expires_at": now + timedelta(hours=1),
    })

    resolved = resolve_server_session(connection, raw_session_id, now=now)

    assert resolved.session_id == "legacy-session"
    assert resolved.active_household_id == "1"
    assert resolved.context_type == "regular"
    assert resolved.role == "admin"
    assert resolved.session_version == 3


def test_legacy_schema_upgrade_rolls_back_completely_on_copy_failure():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        create_legacy_server_sessions_schema(conn)
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        conn.commit()
        before = conn.execute(text("SELECT * FROM server_sessions")).all()

        def fail_during_copy(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().startswith(
                "INSERT INTO server_sessions__context_foundation"
            ):
                raise RuntimeError("forced isolated copy failure")

        event.listen(engine, "before_cursor_execute", fail_during_copy)
        try:
            with pytest.raises(RuntimeError, match="forced isolated copy failure"):
                ensure_server_session_schema(conn)
        finally:
            event.remove(engine, "before_cursor_execute", fail_during_copy)

        after = conn.execute(text("SELECT * FROM server_sessions")).all()
        household_column = next(
            column for column in inspect(conn).get_columns("server_sessions")
            if column["name"] == "active_household_id"
        )
        temporary_exists = inspect(conn).has_table(
            "server_sessions__context_foundation"
        )

    assert after == before
    assert household_column["nullable"] is False
    assert temporary_exists is False


def test_legacy_schema_upgrade_rolls_back_completely_after_table_swap():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        create_legacy_server_sessions_schema(conn)
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        conn.commit()
        before_rows = conn.execute(text("SELECT * FROM server_sessions")).all()

        def fail_during_index_restore(
            _conn, _cursor, statement, _parameters, _context, _many
        ):
            if statement.lstrip().startswith(
                "CREATE INDEX idx_server_sessions_user_active"
            ):
                raise RuntimeError("forced isolated post-swap failure")

        event.listen(engine, "before_cursor_execute", fail_during_index_restore)
        try:
            with pytest.raises(
                RuntimeError,
                match="forced isolated post-swap failure",
            ):
                ensure_server_session_schema(conn)
        finally:
            event.remove(engine, "before_cursor_execute", fail_during_index_restore)

        after_rows = conn.execute(text("SELECT * FROM server_sessions")).all()
        columns = {
            column["name"]: column
            for column in inspect(conn).get_columns("server_sessions")
        }
        indexes = {
            index["name"]: index
            for index in inspect(conn).get_indexes("server_sessions")
        }
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO server_sessions(
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at
                ) VALUES ('duplicate', 'hash1', 'u2', '2',
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))

    assert after_rows == before_rows
    assert columns["active_household_id"]["nullable"] is False
    assert columns["id"]["primary_key"] == 1
    assert columns["session_token_hash"]["nullable"] is False
    assert indexes["idx_server_sessions_user_active"]["column_names"] == [
        "user_id",
        "revoked_at",
        "expires_at",
    ]
    assert "server_sessions__context_foundation" not in inspect(engine).get_table_names()


@pytest.mark.parametrize(
    "schema_sql",
    [
        legacy_server_sessions_sql().replace(
            "user_id VARCHAR(64) NOT NULL",
            "user_id TEXT NOT NULL",
        ),
        legacy_server_sessions_sql().replace(
            "issued_at TIMESTAMP NOT NULL",
            "issued_at TIMESTAMP NULL",
        ),
        legacy_server_sessions_sql().replace(
            "session_version INTEGER NOT NULL DEFAULT 1",
            "session_version INTEGER NOT NULL DEFAULT 2",
        ),
        legacy_server_sessions_sql().replace(
            "id VARCHAR(64) PRIMARY KEY",
            "id VARCHAR(64)",
        ),
        legacy_server_sessions_sql()
        .replace(
            "active_household_id VARCHAR(64) NOT NULL",
            "active_household_id VARCHAR(64) NULL",
        )
        .replace(
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ),
    ],
    ids=[
        "wrong-type",
        "wrong-nullability",
        "wrong-default",
        "missing-primary-key",
        "nullable-but-corrupt",
    ],
)
def test_schema_contract_rejects_corruption_without_data_loss(schema_sql):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(schema_sql))
        conn.execute(text("""
            CREATE INDEX idx_server_sessions_user_active
            ON server_sessions(user_id, revoked_at, expires_at)
        """))
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        assert_failed_upgrade_preserves_schema_and_data(conn)


def test_schema_contract_rejects_wrong_named_index_without_data_loss():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(legacy_server_sessions_sql()))
        conn.execute(text("""
            CREATE INDEX idx_server_sessions_user_active
            ON server_sessions(user_id, expires_at, revoked_at)
        """))
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        assert_failed_upgrade_preserves_schema_and_data(conn)


def test_schema_contract_rejects_missing_token_hash_unique_without_data_loss():
    engine = create_engine("sqlite:///:memory:")
    schema_sql = legacy_server_sessions_sql().replace(
        "session_token_hash VARCHAR(64) NOT NULL UNIQUE",
        "session_token_hash VARCHAR(64) NOT NULL",
    )
    with engine.begin() as conn:
        conn.execute(text(schema_sql))
        conn.execute(text("""
            CREATE INDEX idx_server_sessions_user_active
            ON server_sessions(user_id, revoked_at, expires_at)
        """))
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        assert_failed_upgrade_preserves_schema_and_data(conn)


def test_schema_contract_rejects_preexisting_temporary_table():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        create_legacy_server_sessions_schema(conn)
        conn.execute(text("""
            CREATE TABLE server_sessions__context_foundation (
                marker TEXT NOT NULL
            )
        """))
        with pytest.raises(
            RuntimeError,
            match="contextfoundationtabel bestaat al",
        ):
            ensure_server_session_schema(conn)
        assert inspect(conn).has_table("server_sessions") is True
        assert inspect(conn).has_table(
            "server_sessions__context_foundation"
        ) is True
