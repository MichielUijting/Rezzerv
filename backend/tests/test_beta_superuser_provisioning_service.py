from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    evaluate_household_permission,
    evaluate_platform_permission,
)
from app.services.beta_superuser_provisioning_service import (
    BetaSuperuserProvisioningError,
    provision_po_beta_superuser,
)


def make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                active INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("INSERT INTO app_users(id, email) VALUES ('user-po', 'po@rezzerv.local')"))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_id)
            VALUES ('membership-po', '0', 'user-po')
        """))
    return engine


def test_provisioning_grants_owner_and_superuser_in_household_zero_and_is_idempotent():
    engine = make_engine()
    with engine.begin() as conn:
        first = provision_po_beta_superuser(conn, email="PO@rezzerv.local", household_id="0")
        second = provision_po_beta_superuser(conn, email="po@rezzerv.local", household_id="0")

        assert first.household_id == "0"
        assert first.household_role_created_or_updated is True
        assert first.platform_role_created_or_updated is True
        assert second.household_role_created_or_updated is False
        assert second.platform_role_created_or_updated is False

        assert evaluate_household_permission(
            conn,
            household_id="0",
            membership_id="membership-po",
            permission_key="members.manage",
        ).allowed
        assert evaluate_household_permission(
            conn,
            household_id="0",
            membership_id="membership-po",
            permission_key="inventory.update",
        ).allowed
        assert evaluate_platform_permission(
            conn,
            user_id="user-po",
            permission_key="platform.frontteam.manage",
        ).allowed
        assert evaluate_platform_permission(
            conn,
            user_id="user-po",
            permission_key="platform.support_access.mutate",
        ).allowed

        household_role = conn.execute(text("""
            SELECT role_key FROM auth_membership_roles
            WHERE household_id = '0' AND membership_id = 'membership-po'
        """)).scalar_one()
        platform_role = conn.execute(text("""
            SELECT role_key FROM auth_platform_user_roles
            WHERE user_id = 'user-po' AND active = 1
        """)).scalar_one()
        assert household_role == "huishouden.eigenaar"
        assert platform_role == "platform.supergebruiker"
        assert conn.execute(text("SELECT COUNT(*) FROM auth_platform_user_roles")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM auth_membership_roles")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM auth_audit_log")).scalar_one() == 2


def test_provisioning_does_not_grant_access_to_another_household():
    engine = make_engine()
    with engine.begin() as conn:
        provision_po_beta_superuser(conn, email="po@rezzerv.local", household_id="0")
        decision = evaluate_household_permission(
            conn,
            household_id="1",
            membership_id="membership-po",
            permission_key="inventory.view",
        )
        assert decision.allowed is False


def test_multiple_households_require_explicit_household_id():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_id)
            VALUES ('membership-po-2', '1', 'user-po')
        """))
        try:
            provision_po_beta_superuser(conn, email="po@rezzerv.local")
        except BetaSuperuserProvisioningError as exc:
            assert "--household-id" in str(exc)
        else:
            raise AssertionError("Meerdere huishoudens moeten een expliciete keuze vereisen")

        result = provision_po_beta_superuser(
            conn,
            email="po@rezzerv.local",
            household_id="0",
        )
        assert result.household_id == "0"


def test_unknown_user_fails_closed_without_partial_grants():
    engine = make_engine()
    with engine.begin() as conn:
        try:
            provision_po_beta_superuser(conn, email="onbekend@rezzerv.local", household_id="0")
        except BetaSuperuserProvisioningError:
            pass
        else:
            raise AssertionError("Onbekende gebruiker moet worden geweigerd")
        assert conn.execute(text("SELECT COUNT(*) FROM auth_platform_user_roles")).scalar_one() == 0
