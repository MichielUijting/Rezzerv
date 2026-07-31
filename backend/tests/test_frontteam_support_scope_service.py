from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.frontteam_support_scope_service import (
    assert_support_household_allowed,
    resolve_support_household_scope,
)
from app.services.platform_actor_service import PlatformActor


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_memberships (
                household_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """))
    return engine


def _actor(role_key: str, email: str = "frontteam@rezzerv.local") -> PlatformActor:
    role = "Supergebruiker" if role_key == "platform.supergebruiker" else "Frontteam"
    return PlatformActor(
        user_id=email,
        email=email,
        name=email,
        role=role,
        role_key=role_key,
    )


def test_supergebruiker_heeft_onbeperkt_meldingenbereik():
    engine = _engine()
    with engine.begin() as conn:
        scope = resolve_support_household_scope(
            conn,
            actor=_actor("platform.supergebruiker", "supergebruiker@rezzerv.local"),
        )
        assert scope.unrestricted is True
        assert scope.allows("0") is True
        assert scope.allows("999") is True


def test_frontteam_heeft_huishouden_nul_en_eigen_huishouden():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES ('7', 'frontteam@rezzerv.local', 'member')
        """))
        scope = resolve_support_household_scope(
            conn,
            actor=_actor("platform.frontteam"),
        )
        assert scope.unrestricted is False
        assert scope.household_ids == ("0", "7")
        assert scope.allows("0") is True
        assert scope.allows("7") is True
        assert scope.allows("8") is False


def test_frontteam_met_meerdere_lidmaatschappen_krijgt_alleen_die_huishoudens():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES
                ('11', 'frontteam@rezzerv.local', 'owner'),
                ('12', 'frontteam@rezzerv.local', 'viewer'),
                ('99', 'ander@rezzerv.local', 'owner')
        """))
        scope = resolve_support_household_scope(
            conn,
            actor=_actor("platform.frontteam"),
        )
        assert scope.household_ids == ("0", "11", "12")
        assert scope.allows("99") is False


def test_frontteam_zonder_lidmaatschap_heeft_alleen_huishouden_nul():
    engine = _engine()
    with engine.begin() as conn:
        scope = resolve_support_household_scope(
            conn,
            actor=_actor("platform.frontteam"),
        )
        assert scope.household_ids == ("0",)
        assert scope.allows("0") is True
        assert scope.allows("1") is False


def test_vreemd_huishouden_wordt_server_side_geweigerd():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES ('7', 'frontteam@rezzerv.local', 'member')
        """))
        with pytest.raises(HTTPException) as exc:
            assert_support_household_allowed(
                conn,
                actor=_actor("platform.frontteam"),
                household_id="8",
            )
        assert exc.value.status_code == 403
        assert "huishouden 0 en eigen huishoudens" in str(exc.value.detail)


def test_ontbrekend_huishouden_wordt_afgekeurd():
    engine = _engine()
    with engine.begin() as conn:
        with pytest.raises(HTTPException) as exc:
            assert_support_household_allowed(
                conn,
                actor=_actor("platform.frontteam"),
                household_id="",
            )
        assert exc.value.status_code == 400
