from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api import superuser_routes
from app.services.authorization_foundation_service import ensure_authorization_foundation


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:")


def test_superuser_gate_requires_active_platform_superuser_role(monkeypatch):
    engine = _engine()
    context = SimpleNamespace(user_id="super-1")
    monkeypatch.setattr(superuser_routes, "resolve_server_session", lambda _conn, _raw: context)

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        with pytest.raises(HTTPException) as exc:
            superuser_routes._require_platform_superuser(conn, "opaque-cookie")
        assert exc.value.status_code == 403

        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('super-1', 'platform.superuser', 1)
        """))
        granted = superuser_routes._require_platform_superuser(conn, "opaque-cookie")
        assert granted.user_id == "super-1"


def test_inactive_superuser_role_is_denied(monkeypatch):
    engine = _engine()
    context = SimpleNamespace(user_id="super-2")
    monkeypatch.setattr(superuser_routes, "resolve_server_session", lambda _conn, _raw: context)

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('super-2', 'platform.superuser', 0)
        """))
        with pytest.raises(HTTPException) as exc:
            superuser_routes._require_platform_superuser(conn, "opaque-cookie")
        assert exc.value.status_code == 403


def test_superuser_foundation_exposes_read_only_tabs():
    assert superuser_routes.SUPERUSER_TABS == (
        "Overzicht",
        "Huishoudens",
        "Gebruik",
        "Kassabonnen",
        "Systeem",
    )
