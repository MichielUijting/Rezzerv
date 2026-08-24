import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.external_database_route_authorization import (
    authorize_external_database_request,
    required_external_database_permission,
)


def build_connection():
    engine = create_engine("sqlite:///:memory:")
    conn = engine.connect()
    ensure_authorization_foundation(conn)
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES
          ('frontteam', 'platform.frontteam', 1),
          ('platform-admin', 'platform.platform_admin', 1),
          ('superuser', 'platform.superuser', 1),
          ('ip-owner', 'platform.ip_owner', 1)
    """))
    conn.commit()
    return engine, conn


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("GET", "/api/external-databases/summary", "platform.external_products.view"),
        ("GET", "/api/external-databases/candidates", "platform.external_products.view"),
        ("POST", "/api/external-databases/retailers/lidl/match-preview", "platform.external_products.search"),
        ("POST", "/api/external-databases/retailers/lidl/diagnose-real-candidates", "platform.external_products.search"),
        ("POST", "/api/external-databases/off/search-preview", "platform.external_products.search"),
        ("POST", "/api/external-databases/coverage/receipt-items", "platform.external_products.search"),
        ("POST", "/api/external-products/off/search", "platform.external_products.search"),
        ("POST", "/api/external-databases/retailers/lidl/save-candidates", "platform.external_products.link_existing"),
        ("POST", "/api/external-databases/candidates/confirm-external", "platform.external_products.link_existing"),
        ("POST", "/api/external-databases/catalog/promote-candidate", "platform.external_products.link_existing"),
        ("POST", "/api/external-databases/catalog/unlink", "platform.external_products.link_existing"),
    ],
)
def test_external_database_route_permission_mapping(method, path, permission):
    assert required_external_database_permission(method, path) == permission


def test_unrelated_and_cors_preflight_requests_are_not_claimed_by_policy():
    assert required_external_database_permission("GET", "/api/session") is None
    assert required_external_database_permission("POST", "/api/receipts") is None
    assert required_external_database_permission("OPTIONS", "/api/external-databases/summary") is None
    assert required_external_database_permission("OPTIONS", "/api/external-databases/off/save-candidates") is None


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/external-databases/summary"),
        ("POST", "/api/external-databases/retailers/lidl/match-preview"),
        ("POST", "/api/external-databases/retailers/lidl/save-candidates"),
    ],
)
def test_frontteam_platform_role_can_use_all_intended_external_database_capabilities(method, path):
    engine, conn = build_connection()
    try:
        permission = authorize_external_database_request(
            conn,
            user_id="frontteam",
            method=method,
            path=path,
        )
        assert permission == required_external_database_permission(method, path)
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.parametrize("user_id", ["regular-admin", "platform-admin"])
def test_roles_without_v2_external_product_permission_are_denied(user_id):
    engine, conn = build_connection()
    try:
        with pytest.raises(HTTPException) as exc:
            authorize_external_database_request(
                conn,
                user_id=user_id,
                method="GET",
                path="/api/external-databases/summary",
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Onvoldoende platformbevoegdheid voor externe databases"
    finally:
        conn.close()
        engine.dispose()


def test_superuser_v2_can_use_functional_external_product_capabilities():
    engine, conn = build_connection()
    try:
        for method, path in (
            ("GET", "/api/external-databases/summary"),
            ("POST", "/api/external-databases/retailers/lidl/match-preview"),
            ("POST", "/api/external-databases/catalog/unlink"),
        ):
            assert authorize_external_database_request(
                conn,
                user_id="superuser",
                method=method,
                path=path,
            ) == required_external_database_permission(method, path)
    finally:
        conn.close()
        engine.dispose()


def test_ip_owner_existing_platform_permission_matrix_is_honored_without_special_case():
    engine, conn = build_connection()
    try:
        for method, path in (
            ("GET", "/api/external-databases/summary"),
            ("POST", "/api/external-databases/retailers/lidl/match-preview"),
            ("POST", "/api/external-databases/catalog/unlink"),
        ):
            assert authorize_external_database_request(
                conn,
                user_id="ip-owner",
                method=method,
                path=path,
            ) == required_external_database_permission(method, path)
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_permission_revocation_fails_closed_immediately():
    engine, conn = build_connection()
    try:
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'frontteam' AND role_key = 'platform.frontteam'
        """))
        with pytest.raises(HTTPException) as exc:
            authorize_external_database_request(
                conn,
                user_id="frontteam",
                method="GET",
                path="/api/external-databases/summary",
            )
        assert exc.value.status_code == 403
    finally:
        conn.close()
        engine.dispose()
