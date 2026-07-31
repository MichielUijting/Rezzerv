import sys
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import app
from app.api import platform_access_routes as routes
from app.services.authorization_foundation_service import ensure_authorization_foundation


def make_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
    return engine


def install_runtime_user(monkeypatch, email: str):
    fake_main = SimpleNamespace(
        get_current_user_from_authorization=lambda authorization: {
            "email": email,
            "role": "owner",
        }
    )
    monkeypatch.setitem(sys.modules, "app.main", fake_main)
    monkeypatch.setattr(app, "main", fake_main, raising=False)


def test_supergebruiker_krijgt_toegang(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(routes, "engine", engine)
    install_runtime_user(monkeypatch, "supergebruiker@rezzerv.local")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('supergebruiker@rezzerv.local', 'platform.supergebruiker', 1)
        """))

    result = routes.get_platform_access(
        bevoegdheid="platform.catalog.view",
        authorization="Bearer token",
    )
    assert result["toegang"] is True
    assert result["rol"] == "Supergebruiker"


def test_frontteam_krijgt_catalogustoegang(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(routes, "engine", engine)
    install_runtime_user(monkeypatch, "frontteam@rezzerv.local")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('frontteam@rezzerv.local', 'platform.frontteam', 1)
        """))

    result = routes.get_platform_access(
        bevoegdheid="platform.catalog.view",
        authorization="Bearer token",
    )
    assert result["toegang"] is True
    assert result["rol"] == "Frontteam"


def test_gewone_eigenaar_zonder_centrale_rol_wordt_geweigerd(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(routes, "engine", engine)
    install_runtime_user(monkeypatch, "eigenaar@rezzerv.local")

    try:
        routes.get_platform_access(
            bevoegdheid="platform.catalog.view",
            authorization="Bearer token",
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "centrale bevoegdheid" in str(exc.detail).lower()
    else:
        raise AssertionError("Een gewone Eigenaar mag geen centrale toegang krijgen")


def test_onbekende_bevoegdheid_wordt_geweigerd_voordat_toegang_wordt_bepaald():
    try:
        routes.get_platform_access(
            bevoegdheid="platform.onbekend",
            authorization="Bearer token",
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "onbekende centrale bevoegdheid" in str(exc.detail).lower()
    else:
        raise AssertionError("Een onbekende centrale bevoegdheid moet worden geweigerd")
