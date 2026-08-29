from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, inspect, text

from app.services.authorization_foundation_service import (
    evaluate_household_permission,
    evaluate_platform_permission,
)
from app.services.beta_superuser_provisioning_service import (
    BetaSuperuserProvisioningError,
    provision_po_beta_superuser,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _insert_membership(
    conn,
    *,
    membership_id: str,
    household_id: str,
    user_id: str,
    email: str,
) -> None:
    """Populate the actual migrated legacy-membership shape used by this checkout."""
    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_memberships")
    }
    membership_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    user_column = _pick(columns, "user_id")
    email_column = _pick(columns, "user_email", "email")
    role_column = _pick(columns, "role", "rol")
    status_column = _pick(columns, "status", "membership_status")
    active_column = _pick(columns, "active", "is_active")

    if not membership_column or not household_column or (not user_column and not email_column):
        raise AssertionError(
            "Gemigreerde household_memberships mist een bruikbare canonical fixture-identiteit"
        )

    values: dict[str, object] = {
        membership_column: membership_id,
        household_column: household_id,
    }
    if user_column:
        values[user_column] = user_id
    if email_column:
        values[email_column] = email
    if role_column:
        values[role_column] = "admin"
    if status_column:
        values[status_column] = "active"
    if active_column:
        values[active_column] = 1

    column_sql = ", ".join(values)
    bind_sql = ", ".join(f":{column}" for column in values)
    conn.execute(
        text(f"INSERT INTO household_memberships ({column_sql}) VALUES ({bind_sql})"),
        values,
    )


def make_engine():
    fd, database_path_raw = tempfile.mkstemp(prefix="rezzerv-po-beta-", suffix=".sqlite")
    os.close(fd)
    database_path = Path(database_path_raw)
    database_path.unlink(missing_ok=True)
    database_url = f"sqlite:///{database_path.as_posix()}"

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Alembic-first PO beta fixture kon niet naar head migreren:\n"
            + result.stdout
            + result.stderr
        )

    engine = create_engine(database_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO app_users(id, email, password)
            VALUES ('user-po', 'po@rezzerv.local', 'po-beta-fixture-password')
        """))
        _insert_membership(
            conn,
            membership_id="membership-po",
            household_id="household-beta",
            user_id="user-po",
            email="po@rezzerv.local",
        )
    return engine


def test_provisioning_grants_household_admin_and_platform_superuser_and_is_idempotent():
    engine = make_engine()
    with engine.begin() as conn:
        first = provision_po_beta_superuser(conn, email="PO@rezzerv.local")
        second = provision_po_beta_superuser(conn, email="po@rezzerv.local")

        assert first.household_role_created_or_updated is True
        assert first.platform_role_created_or_updated is True
        assert second.household_role_created_or_updated is False
        assert second.platform_role_created_or_updated is False

        assert evaluate_household_permission(
            conn,
            household_id="household-beta",
            membership_id="membership-po",
            permission_key="permissions.manage",
        ).allowed
        assert evaluate_household_permission(
            conn,
            household_id="household-beta",
            membership_id="membership-po",
            permission_key="inventory.correct",
        ).allowed
        assert evaluate_platform_permission(
            conn,
            user_id="user-po",
            permission_key="platform.permissions.manage",
        ).allowed
        assert evaluate_platform_permission(
            conn,
            user_id="user-po",
            permission_key="platform.support_access.mutate",
        ).allowed

        assert conn.execute(text("SELECT COUNT(*) FROM auth_platform_user_roles")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM auth_membership_roles")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM auth_audit_log")).scalar_one() == 2


def test_provisioning_does_not_grant_access_to_another_household():
    engine = make_engine()
    with engine.begin() as conn:
        provision_po_beta_superuser(conn, email="po@rezzerv.local")
        decision = evaluate_household_permission(
            conn,
            household_id="household-other",
            membership_id="membership-po",
            permission_key="inventory.view",
        )
        assert decision.allowed is False


def test_multiple_households_require_explicit_household_id():
    engine = make_engine()
    with engine.begin() as conn:
        _insert_membership(
            conn,
            membership_id="membership-po-2",
            household_id="household-other",
            user_id="user-po",
            email="po@rezzerv.local",
        )
        try:
            provision_po_beta_superuser(conn, email="po@rezzerv.local")
        except BetaSuperuserProvisioningError as exc:
            assert "--household-id" in str(exc)
        else:
            raise AssertionError("Meerdere huishoudens moeten een expliciete keuze vereisen")

        result = provision_po_beta_superuser(
            conn,
            email="po@rezzerv.local",
            household_id="household-beta",
        )
        assert result.household_id == "household-beta"


def test_unknown_user_fails_closed_without_partial_grants():
    engine = make_engine()
    with engine.begin() as conn:
        try:
            provision_po_beta_superuser(conn, email="onbekend@rezzerv.local")
        except BetaSuperuserProvisioningError:
            pass
        else:
            raise AssertionError("Onbekende gebruiker moet worden geweigerd")
        assert conn.execute(text("SELECT COUNT(*) FROM auth_platform_user_roles")).scalar_one() == 0
