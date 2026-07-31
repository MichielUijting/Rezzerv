from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    HOUSEHOLD_PERMISSIONS,
    PLATFORM_PERMISSIONS,
    assert_owner_remains,
    ensure_authorization_foundation,
    evaluate_household_permission,
    evaluate_platform_permission,
    is_frontteam_member,
    set_frontteam_membership,
    write_authorization_audit,
)


def make_engine():
    return create_engine("sqlite+pysqlite:///:memory:")


def test_registry_and_dutch_roles_are_seeded_idempotently():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        ensure_authorization_foundation(conn)
        permission_count = conn.execute(text("SELECT COUNT(*) FROM auth_permissions")).scalar_one()
        active_roles = conn.execute(text("SELECT role_key FROM auth_roles WHERE active = 1 ORDER BY role_key")).scalars().all()
    assert permission_count == len(HOUSEHOLD_PERMISSIONS) + len(PLATFORM_PERMISSIONS)
    assert active_roles == [
        "huishouden.eigenaar",
        "huishouden.kijker",
        "huishouden.lid",
        "platform.frontteam",
        "platform.supergebruiker",
    ]


def test_eigenaar_receives_all_household_rights_but_no_platform_rights():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('huishouden-a', 'eigenaar-1', 'huishouden.eigenaar')
        """))
        for permission_key in HOUSEHOLD_PERMISSIONS:
            decision = evaluate_household_permission(
                conn,
                household_id="huishouden-a",
                membership_id="eigenaar-1",
                permission_key=permission_key,
            )
            assert decision.allowed, permission_key
        wrong_scope = evaluate_household_permission(
            conn,
            household_id="huishouden-a",
            membership_id="eigenaar-1",
            permission_key="platform.audit.view",
        )
    assert not wrong_scope.allowed
    assert wrong_scope.reason == "onbekende_of_verkeerde_reikwijdte"


def test_explicit_deny_wins_and_allow_can_extend_lid():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('huishouden-a', 'lid-1', 'huishouden.lid')
        """))
        conn.execute(text("""
            INSERT INTO auth_membership_permission_overrides(
                household_id, membership_id, permission_key, effect, reason
            ) VALUES
                ('huishouden-a', 'lid-1', 'inventory.update', 'deny', 'alleen lezen'),
                ('huishouden-a', 'lid-1', 'receipts.delete', 'allow', 'vertrouwd lid')
        """))
        denied = evaluate_household_permission(conn, household_id="huishouden-a", membership_id="lid-1", permission_key="inventory.update")
        extended = evaluate_household_permission(conn, household_id="huishouden-a", membership_id="lid-1", permission_key="receipts.delete")
    assert denied.allowed is False
    assert denied.reason == "expliciet_geweigerd"
    assert extended.allowed is True
    assert extended.reason == "expliciet_toegestaan"


def test_household_context_is_strictly_isolated():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('huishouden-a', 'eigenaar-1', 'huishouden.eigenaar')
        """))
        same_household = evaluate_household_permission(conn, household_id="huishouden-a", membership_id="eigenaar-1", permission_key="inventory.update")
        other_household = evaluate_household_permission(conn, household_id="huishouden-b", membership_id="eigenaar-1", permission_key="inventory.update")
    assert same_household.allowed is True
    assert other_household.allowed is False


def test_unknown_permission_is_denied_by_default():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        decision = evaluate_household_permission(conn, household_id="huishouden-a", membership_id="lid-1", permission_key="inventory.destroy_everything")
    assert decision.allowed is False
    assert decision.reason == "onbekende_of_verkeerde_reikwijdte"


def test_multiple_platform_roles_are_combined_with_or_rule():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('gebruiker-1', 'platform.frontteam')
        """))
        catalog = evaluate_platform_permission(conn, user_id="gebruiker-1", permission_key="platform.catalog.update")
        support = evaluate_platform_permission(conn, user_id="gebruiker-1", permission_key="platform.support_access.mutate")
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('gebruiker-1', 'platform.supergebruiker')
        """))
        support_after_second_role = evaluate_platform_permission(conn, user_id="gebruiker-1", permission_key="platform.support_access.mutate")
    assert catalog.allowed is True
    assert catalog.granted_by == "platform.frontteam"
    assert support.allowed is False
    assert support_after_second_role.allowed is True
    assert support_after_second_role.granted_by == "platform.supergebruiker"


def test_only_superuser_can_toggle_frontteam_through_service_contract():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        assert is_frontteam_member(conn, user_id="lid@rezzerv.local") is False
        set_frontteam_membership(conn, user_id="lid@rezzerv.local", active=True)
        assert is_frontteam_member(conn, user_id="lid@rezzerv.local") is True
        set_frontteam_membership(conn, user_id="lid@rezzerv.local", active=False)
        assert is_frontteam_member(conn, user_id="lid@rezzerv.local") is False


def test_owner_cannot_be_removed_before_transfer():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('huishouden-a', 'eigenaar-1', 'huishouden.eigenaar')
        """))
        with pytest.raises(ValueError, match="Draag het eigenaarschap eerst over"):
            assert_owner_remains(conn, household_id="huishouden-a", membership_id_to_remove="eigenaar-1")


def test_authorization_audit_is_append_only_by_service_contract():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        first_id = write_authorization_audit(
            conn,
            actor_user_id="supergebruiker@rezzerv.local",
            actor_type="Supergebruiker",
            action="Frontteam toegevoegd",
            object_type="Rezzerv-gebruiker",
            object_id="lid@rezzerv.local",
            old_value={"Frontteam": False},
            new_value={"Frontteam": True},
        )
        second_id = write_authorization_audit(
            conn,
            actor_user_id="supergebruiker@rezzerv.local",
            actor_type="Supergebruiker",
            action="Frontteam verwijderd",
            object_type="Rezzerv-gebruiker",
            object_id="lid@rezzerv.local",
            old_value={"Frontteam": True},
            new_value={"Frontteam": False},
        )
        rows = conn.execute(text("SELECT id, action FROM auth_audit_log ORDER BY created_at, id")).mappings().all()
    assert first_id != second_id
    assert len(rows) == 2
    assert {row["action"] for row in rows} == {"Frontteam toegevoegd", "Frontteam verwijderd"}
