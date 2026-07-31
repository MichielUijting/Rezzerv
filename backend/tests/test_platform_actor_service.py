from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.platform_actor_service import (
    SUPERGEBRUIKER_EMAIL,
    PlatformActor,
    assert_platform_household_mutation_allowed,
    resolve_platform_actor,
)


def make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
    return engine


def test_huishoudrol_admin_verleent_geen_centrale_toegang():
    engine = make_engine()
    with engine.begin() as conn:
        try:
            resolve_platform_actor(
                conn,
                runtime_user={"email": "admin@rezzerv.local", "role": "admin"},
                permission_key="platform.users.view",
            )
        except HTTPException as exc:
            assert exc.status_code == 403
            assert "centrale bevoegdheid" in str(exc.detail).lower()
        else:
            raise AssertionError("Een huishoudrol mag geen centrale toegang verlenen")


def test_supergebruiker_wordt_via_centrale_rol_herkend():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES (:user_id, 'platform.supergebruiker', 1)
        """), {"user_id": SUPERGEBRUIKER_EMAIL})
        actor = resolve_platform_actor(
            conn,
            runtime_user={"email": SUPERGEBRUIKER_EMAIL, "role": "owner"},
            permission_key="platform.users.view",
        )
    assert actor.role == "Supergebruiker"
    assert actor.is_supergebruiker is True
    assert actor.is_frontteam is False


def test_frontteam_wordt_via_aanvullende_centrale_rol_herkend():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('lid@rezzerv.local', 'platform.frontteam', 1)
        """))
        actor = resolve_platform_actor(
            conn,
            runtime_user={"email": "lid@rezzerv.local", "role": "member"},
            permission_key="platform.catalog.view",
        )
    assert actor.role == "Frontteam"
    assert actor.is_frontteam is True


def test_supergebruiker_mag_huishouden_0_wijzigen():
    actor = PlatformActor(
        user_id=SUPERGEBRUIKER_EMAIL,
        email=SUPERGEBRUIKER_EMAIL,
        name="Supergebruiker",
        role="Supergebruiker",
        role_key="platform.supergebruiker",
    )
    assert_platform_household_mutation_allowed(actor=actor, household_id="0")


def test_supergebruiker_mag_geen_ander_huishouden_wijzigen():
    actor = PlatformActor(
        user_id=SUPERGEBRUIKER_EMAIL,
        email=SUPERGEBRUIKER_EMAIL,
        name="Supergebruiker",
        role="Supergebruiker",
        role_key="platform.supergebruiker",
    )
    try:
        assert_platform_household_mutation_allowed(actor=actor, household_id="1")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "huishouden 0" in str(exc.detail).lower()
    else:
        raise AssertionError("Supergebruiker mag huishouden 1 niet wijzigen")


def test_frontteam_mag_geen_huishoudgegevens_wijzigen():
    actor = PlatformActor(
        user_id="frontteam@rezzerv.local",
        email="frontteam@rezzerv.local",
        name="Frontteam",
        role="Frontteam",
        role_key="platform.frontteam",
    )
    try:
        assert_platform_household_mutation_allowed(actor=actor, household_id="0")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "frontteam" in str(exc.detail).lower()
    else:
        raise AssertionError("Frontteam mag geen huishoudgegevens wijzigen")
