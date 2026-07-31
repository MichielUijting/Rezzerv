from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api.support_message_routes import (
    _platform_export_csv,
    _platform_thread_header,
    _platform_threads,
)
from app.services.platform_actor_service import PlatformActor
from app.services.support_message_service import create_support_thread


ROUTES_SOURCE = Path(__file__).resolve().parents[1] / "app/api/support_message_routes.py"


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


def _actor(role_key: str, email: str) -> PlatformActor:
    return PlatformActor(
        user_id=email,
        email=email,
        name=email,
        role="Supergebruiker" if role_key == "platform.supergebruiker" else "Frontteam",
        role_key=role_key,
    )


def _thread(conn, household_id: str, subject: str):
    return create_support_thread(
        conn,
        created_by_user_id="eigenaar@voorbeeld.nl",
        created_by_name="Eigenaar",
        sender_role="Eigenaar",
        subject=subject,
        message_text="Testbericht",
        origin_screen_name="Testscherm",
        household_id=household_id,
    )


def test_frontteam_overzicht_bevat_alleen_huishouden_nul_en_eigen_huishouden():
    engine = _engine()
    actor = _actor("platform.frontteam", "frontteam@rezzerv.local")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES ('7', 'frontteam@rezzerv.local', 'member')
        """))
        _thread(conn, "0", "Huishouden nul")
        _thread(conn, "7", "Eigen huishouden")
        _thread(conn, "8", "Vreemd huishouden")

        rows = _platform_threads(conn, actor=actor, household_id=None, status=None)

    assert {str(row["household_id"]) for row in rows} == {"0", "7"}
    assert {str(row["subject"]) for row in rows} == {"Huishouden nul", "Eigen huishouden"}


def test_frontteam_kan_vreemde_conversatie_niet_openen():
    engine = _engine()
    actor = _actor("platform.frontteam", "frontteam@rezzerv.local")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES ('7', 'frontteam@rezzerv.local', 'member')
        """))
        foreign_thread = _thread(conn, "8", "Vreemd huishouden")

        with pytest.raises(HTTPException) as exc:
            _platform_thread_header(conn, actor=actor, thread_id=foreign_thread.thread_id)

    assert exc.value.status_code == 403


def test_frontteam_csv_bevat_geen_vreemd_huishouden():
    engine = _engine()
    actor = _actor("platform.frontteam", "frontteam@rezzerv.local")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships (household_id, user_email, role)
            VALUES ('7', 'frontteam@rezzerv.local', 'owner')
        """))
        _thread(conn, "0", "Zichtbaar nul")
        _thread(conn, "7", "Zichtbaar eigen")
        _thread(conn, "8", "Verborgen vreemd")

        csv_text = _platform_export_csv(conn, actor=actor, status=None)

    assert "Zichtbaar nul" in csv_text
    assert "Zichtbaar eigen" in csv_text
    assert "Verborgen vreemd" not in csv_text


def test_supergebruiker_behoudt_volledig_overzicht():
    engine = _engine()
    actor = _actor("platform.supergebruiker", "supergebruiker@rezzerv.local")
    with engine.begin() as conn:
        _thread(conn, "0", "Nul")
        _thread(conn, "7", "Zeven")
        _thread(conn, "8", "Acht")
        rows = _platform_threads(conn, actor=actor, household_id=None, status=None)

    assert {str(row["household_id"]) for row in rows} == {"0", "7", "8"}


def test_alle_centrale_mutatieroutes_roepen_bereikcontrole_aan():
    source = ROUTES_SOURCE.read_text(encoding="utf-8")
    assert "assert_support_household_allowed(conn, actor=actor, household_id=payload.household_id)" in source
    assert source.count("_platform_thread_header(conn, actor=actor, thread_id=thread_id)") >= 3
    assert "_platform_export_csv(conn, actor=actor, status=status)" in source
