from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services import session_request_context
from app.services.authorization_foundation_service import PLATFORM_ADMIN_PERMISSIONS
from app.services.household_reset_service import (
    MANUAL_FK_EDGES,
    PRESERVED_TABLES,
    reset_household_data,
)
from app.services.server_session_service import ServerSessionContext
from app.testing.postgresql_platform_authorization_fixture import (
    cleanup_platform_authorization_test_engine,
    create_platform_authorization_test_engine,
)


PERMISSION = "platform.recovery.manage"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = BACKEND_ROOT / "app" / "api" / "platform_household_reset_routes.py"
SERVICE_SOURCE = BACKEND_ROOT / "app" / "services" / "household_reset_service.py"
FRONTEND_SOURCE = BACKEND_ROOT.parent / "frontend" / "src" / "features" / "platform" / "PlatformRecoveryPage.jsx"


@pytest.fixture
def auth_engine():
    engine = create_platform_authorization_test_engine()
    try:
        yield engine
    finally:
        cleanup_platform_authorization_test_engine(engine)


def _context(user_id: str) -> ServerSessionContext:
    now = datetime.now(timezone.utc)
    if user_id == "superuser":
        context_type = "system"
        household_id = "0"
        role = "owner"
    elif user_id in {"platform-admin", "ip-owner"}:
        context_type = "none"
        household_id = None
        role = None
    else:
        context_type = "regular"
        household_id = "household-1"
        role = "admin" if user_id == "ordinary-admin" else "member"
    return ServerSessionContext(
        session_id=f"session-{user_id}",
        user_id=user_id,
        email=f"{user_id}@example.test",
        active_household_id=household_id,
        context_type=context_type,
        role=role,
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        is_platform_superuser=user_id == "superuser",
        is_platform_admin=user_id == "platform-admin",
        is_ip_owner=user_id == "ip-owner",
    )


def _bind_context(monkeypatch, auth_engine, user_id: str) -> ServerSessionContext:
    context = _context(user_id)
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        lambda: context,
    )
    return context


def test_household_reset_reuses_platform_recovery_permission_only():
    assert PERMISSION in PLATFORM_ADMIN_PERMISSIONS
    assert "platform.household_reset.manage" not in PLATFORM_ADMIN_PERMISSIONS

    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    assert 'PLATFORM_HOUSEHOLD_RESET_PERMISSION = "platform.recovery.manage"' in route_source
    assert 'require_platform_permission_from_session(' in route_source
    assert '@router.post("/api/platform/recovery/reset-household")' in route_source


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("platform-admin", True),
        ("superuser", False),
        ("ip-owner", False),
        ("ordinary-admin", False),
        ("ordinary-member", False),
    ],
)
def test_only_platform_admin_role_has_reset_authority(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    context = _bind_context(monkeypatch, auth_engine, user_id)
    if allowed:
        actual = session_request_context.require_platform_permission_from_session(PERMISSION)
        assert actual is context
        assert actual.context_type == "none"
        return

    with pytest.raises(HTTPException) as exc:
        session_request_context.require_platform_permission_from_session(PERMISSION)
    assert exc.value.status_code == 403


def test_reset_service_preserves_identity_shell_and_audit():
    required = {
        "household_registry",
        "household_memberships",
        "auth_membership_roles",
        "auth_audit_log",
        "app_users",
        "server_sessions",
    }
    assert required.issubset(PRESERVED_TABLES)

    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert 'expected_confirmation = f"RESET {target}"' in source
    assert 'target in FORBIDDEN_HOUSEHOLD_IDS' in source
    assert 'context_type == "system"' in source
    assert "_membership_snapshot" in source
    assert "Lidmaatschappen veranderden onverwacht" in source
    assert "_revoke_household_sessions" in source
    assert "Resetcontrole vond resterende huishouddata" in source
    assert "with engine.begin()" not in source


def test_route_audits_reset_without_exposing_household_content():
    source = ROUTE_SOURCE.read_text(encoding="utf-8")
    assert 'action="platform.household.reset"' in source
    assert 'actor_type="platform_admin"' in source
    assert '"deleted_row_count": result["deleted_row_count"]' in source
    assert '"deleted_tables": sorted(result["deleted_by_table"])' in source
    assert "household_context_used" in source
    assert '"context_type": context.context_type' in source
    assert "password" not in source.lower()


def test_recovery_ui_requires_destructive_confirmation_phrase():
    source = FRONTEND_SOURCE.read_text(encoding="utf-8")
    assert "Huishouden volledig resetten" in source
    assert "RESET ${resetConfirmationTarget}" in source
    assert "/api/platform/recovery/reset-household" in source
    assert "wachtwoord-/inloggegevens" in source
    assert "Systeemhuishouden 0 is uitgesloten" in source
    assert "platform-reset-household-confirmation" in source



def test_legacy_logical_child_relations_are_explicitly_covered():
    expected = {
        ("sublocations", "spaces", ("space_id",), ("id",)),
        ("receipt_table_lines", "receipt_tables", ("receipt_table_id",), ("id",)),
        ("purchase_import_lines", "purchase_import_batches", ("batch_id",), ("id",)),
        ("external_product_candidates", "purchase_import_lines", ("purchase_import_line_id",), ("id",)),
        ("household_article_settings", "household_articles", ("household_article_id",), ("id",)),
        ("household_article_notes", "household_articles", ("household_article_id",), ("id",)),
        ("support_messages", "support_threads", ("thread_id",), ("id",)),
    }
    actual = {
        (child, edge.parent_table, edge.local_columns, edge.parent_columns)
        for child, edges in MANUAL_FK_EDGES.items()
        for edge in edges
    }
    assert expected.issubset(actual)


def test_postgresql_reset_removes_target_data_but_preserves_identity_and_other_household(auth_engine):
    target = f"reset-{uuid.uuid4().hex[:12]}"
    other = f"other-{uuid.uuid4().hex[:12]}"
    target_user_id = f"user-{uuid.uuid4().hex}"
    target_email = f"{target_user_id}@example.test"
    target_membership_id = f"membership-{uuid.uuid4().hex}"
    target_space = f"space-{uuid.uuid4().hex}"
    target_sublocation = f"sublocation-{uuid.uuid4().hex}"
    other_space = f"space-{uuid.uuid4().hex}"
    other_sublocation = f"sublocation-{uuid.uuid4().hex}"
    session_id = f"session-{uuid.uuid4().hex}"
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    try:
        with auth_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO household_registry(id, naam, context_type, created_at)
                    VALUES (:id, :name, 'regular', CURRENT_TIMESTAMP)
                    """
                ),
                {"id": target, "name": "Reset test household"},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO household_registry(id, naam, context_type, created_at)
                    VALUES (:id, :name, 'regular', CURRENT_TIMESTAMP)
                    """
                ),
                {"id": other, "name": "Other test household"},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO app_users(id, email, password, created_at, updated_at)
                    VALUES (:id, :email, 'KeepThisLoginSecret', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {"id": target_user_id, "email": target_email},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO household_memberships(
                        id, household_id, user_email, user_id, role, created_at, updated_at
                    ) VALUES (
                        :id, :household_id, :email, :user_id, 'admin',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": target_membership_id,
                    "household_id": target,
                    "email": target_email,
                    "user_id": target_user_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO auth_membership_roles(
                        household_id, membership_id, role_key, active, created_at, updated_at
                    ) VALUES (
                        :household_id, :membership_id, 'household.admin',
                        TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"household_id": target, "membership_id": target_membership_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO spaces(id, naam, household_id, active)
                    VALUES (:id, 'Target room', :household_id, TRUE)
                    """
                ),
                {"id": target_space, "household_id": target},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO sublocations(id, naam, space_id, active)
                    VALUES (:id, 'Target shelf', :space_id, TRUE)
                    """
                ),
                {"id": target_sublocation, "space_id": target_space},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO spaces(id, naam, household_id, active)
                    VALUES (:id, 'Other room', :household_id, TRUE)
                    """
                ),
                {"id": other_space, "household_id": other},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO sublocations(id, naam, space_id, active)
                    VALUES (:id, 'Other shelf', :space_id, TRUE)
                    """
                ),
                {"id": other_sublocation, "space_id": other_space},
            )
            now = datetime.now(timezone.utc)
            conn.execute(
                text(
                    """
                    INSERT INTO server_sessions(
                        id, session_token_hash, user_id, active_household_id,
                        issued_at, expires_at, session_version, revoked_at,
                        replaced_by_session_id, created_at, updated_at
                    ) VALUES (
                        :id, :token_hash, :user_id, :household_id,
                        :issued_at, :expires_at, 1, NULL, NULL, :issued_at, :issued_at
                    )
                    """
                ),
                {
                    "id": session_id,
                    "token_hash": token_hash,
                    "user_id": target_user_id,
                    "household_id": target,
                    "issued_at": now,
                    "expires_at": now + timedelta(hours=1),
                },
            )

        with auth_engine.begin() as conn:
            result = reset_household_data(
                conn,
                target,
                confirmation=f"RESET {target}",
            )
            assert result["household_id"] == target
            assert result["preserved_member_count"] == 1
            assert result["sessions_revoked"] == 1
            assert result["deleted_by_table"]["spaces"] == 1
            assert result["deleted_by_table"]["sublocations"] == 1

        with auth_engine.connect() as conn:
            assert conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id=:id"),
                {"id": target},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM sublocations WHERE id=:id"),
                {"id": target_sublocation},
            ).scalar_one() == 0

            assert conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id=:id"),
                {"id": other},
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT COUNT(*) FROM sublocations WHERE id=:id"),
                {"id": other_sublocation},
            ).scalar_one() == 1

            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": target},
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_memberships WHERE id=:id"),
                {"id": target_membership_id},
            ).scalar_one() == 1
            assert conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM auth_membership_roles
                    WHERE household_id=:household_id
                      AND membership_id=:membership_id
                      AND role_key='household.admin'
                      AND active IS TRUE
                    """
                ),
                {"household_id": target, "membership_id": target_membership_id},
            ).scalar_one() == 1
            user = conn.execute(
                text("SELECT email, password FROM app_users WHERE id=:id"),
                {"id": target_user_id},
            ).mappings().one()
            assert user["email"] == target_email
            assert user["password"] == "KeepThisLoginSecret"
            assert conn.execute(
                text("SELECT revoked_at FROM server_sessions WHERE id=:id"),
                {"id": session_id},
            ).scalar_one() is not None
    finally:
        with auth_engine.begin() as conn:
            conn.execute(text("DELETE FROM server_sessions WHERE id=:id"), {"id": session_id})
            conn.execute(
                text("DELETE FROM auth_membership_roles WHERE household_id IN (:target, :other)"),
                {"target": target, "other": other},
            )
            conn.execute(
                text("DELETE FROM household_memberships WHERE household_id IN (:target, :other)"),
                {"target": target, "other": other},
            )
            conn.execute(text("DELETE FROM sublocations WHERE id IN (:target, :other)"), {
                "target": target_sublocation,
                "other": other_sublocation,
            })
            conn.execute(text("DELETE FROM spaces WHERE id IN (:target, :other)"), {
                "target": target_space,
                "other": other_space,
            })
            conn.execute(
                text("DELETE FROM household_registry WHERE id IN (:target, :other)"),
                {"target": target, "other": other},
            )
            conn.execute(text("DELETE FROM app_users WHERE id=:id"), {"id": target_user_id})
