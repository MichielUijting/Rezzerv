from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import platform_feature_flags_routes
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.external_database_route_authorization import authorize_external_database_request
from app.services.platform_feature_flag_service import (
    FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
    ensure_platform_feature_flag_schema,
    set_platform_feature_flag,
)
from app.services.server_session_service import ServerSessionContext


FEATURE_FLAGS_PERMISSION = "platform.feature_flags.manage"


@pytest.fixture
def auth_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        ensure_platform_feature_flag_schema(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('platform-admin', 'platform.platform_admin', 1),
              ('ip-owner', 'platform.ip_owner', 1),
              ('superuser', 'platform.superuser', 1),
              ('support-reader', 'platform.support_read', 1),
              ('frontteam', 'platform.frontteam', 1)
        """))
    try:
        yield engine
    finally:
        engine.dispose()


def _context(user_id: str) -> ServerSessionContext:
    now = datetime.now(timezone.utc)
    if user_id in {"superuser", "ip-owner"}:
        context_type = "system"
        household_id = "0"
        role = "owner"
    elif user_id == "platform-admin":
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
        is_frontteam=user_id == "frontteam",
    )


def _bind_context(monkeypatch, auth_engine, user_id: str) -> ServerSessionContext:
    context = _context(user_id)
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(
        session_request_context,
        "resolve_current_server_session",
        lambda: context,
    )
    monkeypatch.setattr(platform_feature_flags_routes, "engine", auth_engine)
    return context


@pytest.mark.parametrize(
    ("user_id", "allowed"),
    [
        ("platform-admin", True),
        ("ip-owner", True),
        ("superuser", False),
        ("support-reader", False),
        ("frontteam", False),
        ("ordinary-admin", False),
    ],
)
def test_feature_flag_routes_use_exact_canonical_permission_matrix(
    monkeypatch,
    auth_engine,
    user_id,
    allowed,
):
    _bind_context(monkeypatch, auth_engine, user_id)

    if allowed:
        payload = platform_feature_flags_routes.get_platform_feature_flags()
        assert payload["count"] == 1
        return

    with pytest.raises(HTTPException) as exc:
        platform_feature_flags_routes.get_platform_feature_flags()
    assert exc.value.status_code == 403
    assert exc.value.detail == f"Ontbrekende platformpermissie: {FEATURE_FLAGS_PERMISSION}"


def test_default_flag_is_enabled_without_seed_or_get_write(monkeypatch, auth_engine):
    context = _bind_context(monkeypatch, auth_engine, "platform-admin")
    with auth_engine.connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM platform_feature_flags")).scalar_one()

    payload = platform_feature_flags_routes.get_platform_feature_flags()

    with auth_engine.connect() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM platform_feature_flags")).scalar_one()
        columns = {
            str(row[1])
            for row in conn.execute(text("PRAGMA table_info(platform_feature_flags)")).all()
        }

    assert context.context_type == "none"
    assert context.active_household_id is None
    assert before == 0
    assert after == 0
    assert "household_id" not in columns
    assert payload["household_context_used"] is False
    assert payload["context_type"] == "none"
    assert payload["items"] == [
        {
            "key": FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
            "label": "Externe productzoekfunctie",
            "description": (
                "Schakelt platformbreed de externe productzoekroutes die onder "
                "platform.external_products.search vallen."
            ),
            "enabled": True,
            "default_enabled": True,
            "source": "default",
            "updated_by": None,
            "updated_at": None,
        }
    ]


def test_platform_admin_can_persist_override_with_canonical_actor(monkeypatch, auth_engine):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    payload = platform_feature_flags_routes.update_platform_feature_flag(
        FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
        platform_feature_flags_routes.PlatformFeatureFlagUpdateRequest(enabled=False),
    )

    assert payload["household_context_used"] is False
    assert payload["item"]["enabled"] is False
    assert payload["item"]["source"] == "override"
    assert payload["item"]["updated_by"] == "platform-admin"

    reread = platform_feature_flags_routes.get_platform_feature_flags()
    assert reread["items"][0]["enabled"] is False

    with auth_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT flag_key, enabled, updated_by
            FROM platform_feature_flags
            WHERE flag_key = :flag_key
        """), {"flag_key": FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH}).mappings().one()
    assert row["flag_key"] == FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH
    assert bool(row["enabled"]) is False
    assert row["updated_by"] == "platform-admin"


def test_unknown_feature_flag_is_rejected_without_arbitrary_key_creation(monkeypatch, auth_engine):
    _bind_context(monkeypatch, auth_engine, "platform-admin")

    with pytest.raises(HTTPException) as exc:
        platform_feature_flags_routes.update_platform_feature_flag(
            "invented_flag",
            platform_feature_flags_routes.PlatformFeatureFlagUpdateRequest(enabled=False),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Onbekende platformfeatureflag"

    with auth_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM platform_feature_flags")).scalar_one() == 0


def test_external_search_flag_controls_availability_after_existing_permission_check(auth_engine):
    with auth_engine.begin() as conn:
        assert authorize_external_database_request(
            conn,
            user_id="frontteam",
            method="POST",
            path="/api/external-products/off/search",
        ) == "platform.external_products.search"

        set_platform_feature_flag(
            conn,
            FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
            enabled=False,
            updated_by="platform-admin",
        )

        with pytest.raises(HTTPException) as exc:
            authorize_external_database_request(
                conn,
                user_id="frontteam",
                method="POST",
                path="/api/external-products/off/search",
            )
        assert exc.value.status_code == 503
        assert exc.value.detail == "Externe productzoekfunctie is platformbreed uitgeschakeld"

        assert authorize_external_database_request(
            conn,
            user_id="frontteam",
            method="GET",
            path="/api/external-databases/summary",
        ) == "platform.external_products.view"
        assert authorize_external_database_request(
            conn,
            user_id="frontteam",
            method="POST",
            path="/api/external-databases/catalog/unlink",
        ) == "platform.external_products.link_existing"


def test_enabling_flag_never_grants_external_search_permission_to_platform_admin(auth_engine):
    with auth_engine.begin() as conn:
        set_platform_feature_flag(
            conn,
            FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
            enabled=True,
            updated_by="platform-admin",
        )
        with pytest.raises(HTTPException) as exc:
            authorize_external_database_request(
                conn,
                user_id="platform-admin",
                method="POST",
                path="/api/external-products/off/search",
            )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Onvoldoende platformbevoegdheid voor externe databases"


def test_platform_admin_revocation_blocks_next_feature_flag_request(monkeypatch, auth_engine):
    _bind_context(monkeypatch, auth_engine, "platform-admin")
    assert platform_feature_flags_routes.get_platform_feature_flags()["count"] == 1

    with auth_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles
            SET active = 0
            WHERE user_id = 'platform-admin'
              AND role_key = 'platform.platform_admin'
        """))

    with pytest.raises(HTTPException) as exc:
        platform_feature_flags_routes.get_platform_feature_flags()
    assert exc.value.status_code == 403


def test_invalid_server_session_remains_401(monkeypatch, auth_engine):
    monkeypatch.setattr(session_request_context, "engine", auth_engine)
    monkeypatch.setattr(platform_feature_flags_routes, "engine", auth_engine)

    def invalid_session():
        raise HTTPException(status_code=401, detail="Ongeldige of verlopen sessie")

    monkeypatch.setattr(session_request_context, "resolve_current_server_session", invalid_session)

    with pytest.raises(HTTPException) as exc:
        platform_feature_flags_routes.get_platform_feature_flags()
    assert exc.value.status_code == 401
    assert exc.value.detail == "Ongeldige of verlopen sessie"
