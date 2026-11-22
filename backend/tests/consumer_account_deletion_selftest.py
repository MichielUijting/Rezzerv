"""Account deletion acceptance on isolated PostgreSQL, not the PO's runtime."""
from __future__ import annotations

import os
import uuid
from sqlalchemy import text

from app.services.consumer_account_deletion_service import (
    AccountDeletionConflictError,
    AccountDeletionPasswordError,
    CONFIRMATION,
    delete_consumer_account,
    deletion_preview,
)
from app.testing.postgresql_acceptance_foundation import (
    create_postgresql_runtime_test_engine,
    postgresql_acceptance_snapshot,
    reset_postgresql_test_database,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    seed_household,
    seed_membership,
    seed_user,
)


def _id(name):
    return name + "-" + uuid.uuid4().hex


def _count(conn, table, where, params):
    return int(conn.execute(text("SELECT COUNT(*) FROM " + table + " WHERE " + where), params).scalar() or 0)


def run() -> int:
    checks = []
    # This test performs a full reset: strictly GitHub's short-lived test service.
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("TEST_POSTGRES_DB") != "rezzerv_authorization_membership_ci":
        raise RuntimeError("Account deletion acceptance requires the isolated GitHub PostgreSQL test database.")
    snap = postgresql_acceptance_snapshot()
    if snap["database"] != "rezzerv_authorization_membership_ci":
        raise RuntimeError("Unexpected database; refusing destructive test reset.")
    assert snap["datastore"] == "postgresql"
    assert snap["runtime_create"] is False
    checks.append("isolated_postgresql_dml_only")

    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        users = [_id("departing"), _id("oldest"), _id("newest"), _id("outsider")]
        emails = [u + "@example.test" for u in users]
        shared, solo, unrelated = (_id("shared"), _id("solo"), _id("unrelated"))
        departed_membership, oldest_membership, newest_membership = (_id("membership") for _ in range(3))
        with engine.begin() as conn:
            for hid in [shared, solo, unrelated]:
                seed_household(conn, household_id=hid, name=hid)
            for uid, email in zip(users, emails):
                seed_user(conn, user_id=uid, email=email, password="TestPassword123!")
            for uid, date in zip(users, ["2026-11-20", "2023-01-02", "2025-09-11", "2022-01-01"]):
                conn.execute(text("UPDATE app_users SET created_at=CAST(:created_at AS TIMESTAMP) WHERE id=:uid"), {
                    "uid": uid, "created_at": date + " 12:00:00",
                })
            seed_membership(conn, membership_id=departed_membership, household_id=shared,
                            user_id=users[0], email=emails[0], role="admin")
            seed_membership(conn, membership_id=oldest_membership, household_id=shared,
                            user_id=users[1], email=emails[1], role="member")
            seed_membership(conn, membership_id=newest_membership, household_id=shared,
                            user_id=users[2], email=emails[2], role="member")
            seed_membership(conn, membership_id=_id("membership"), household_id=solo,
                            user_id=users[0], email=emails[0], role="admin")
            seed_membership(conn, membership_id=_id("membership"), household_id=unrelated,
                            user_id=users[3], email=emails[3], role="admin")
            for hid in [shared, solo, unrelated]:
                conn.execute(text("INSERT INTO spaces(id, naam, household_id, active) VALUES (:id,'Kast',:hid,TRUE)"), {
                    "id": _id("space"), "hid": hid,
                })
            preview = deletion_preview(conn, user_id=users[0])
            assert preview["households_to_keep"] == 1
            assert preview["households_to_delete"] == 1
        checks.append("multiple_households_preview_correct")

        for bad_confirmation, bad_password, expected_exception in [
            ("NIET VERWIJDEREN", "TestPassword123!", AccountDeletionConflictError),
            (CONFIRMATION, "WrongPassword123!", AccountDeletionPasswordError),
        ]:
            try:
                with engine.begin() as conn:
                    delete_consumer_account(conn, user_id=users[0],
                                            current_password=bad_password,
                                            confirmation=bad_confirmation)
            except expected_exception:
                pass
            else:
                raise AssertionError("Deletion without confirmation/password unexpectedly succeeded")
        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[0]}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": shared}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": solo}) == 1
        checks.append("invalid_credentials_or_confirmation_changes_nothing")

        with engine.begin() as conn:
            result = delete_consumer_account(
                conn, user_id=users[0], current_password="TestPassword123!",
                confirmation=CONFIRMATION,
            )
            assert result["deleted"] is True
            assert result["households_deleted"] == 1
            assert result["households_preserved"] == 1
            assert result["admins_transferred"] == 1
        checks.append("multi_household_deletion_transaction_committed")

        with engine.begin() as conn:
            assert _count(conn, "app_users", "id=:uid", {"uid": users[0]}) == 0
            assert _count(conn, "household_memberships", "lower(trim(user_email))=:email", {"email": emails[0]}) == 0
            assert _count(conn, "household_registry", "id=:hid", {"hid": solo}) == 0
            assert _count(conn, "spaces", "household_id=:hid", {"hid": solo}) == 0
            assert _count(conn, "household_registry", "id=:hid", {"hid": shared}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": shared}) == 1
            assert _count(conn, "household_registry", "id=:hid", {"hid": unrelated}) == 1
            assert _count(conn, "spaces", "household_id=:hid", {"hid": unrelated}) == 1
            role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": shared, "mid": oldest_membership}).scalar_one()
            assert role == "household.admin"
            mirror = conn.execute(text("""
                SELECT role FROM household_memberships WHERE household_id=:hid AND id=:mid
            """), {"hid": shared, "mid": oldest_membership}).scalar_one()
            assert mirror == "admin"
            late_role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id=:hid AND membership_id=:mid
            """), {"hid": shared, "mid": newest_membership}).scalar_one()
            assert late_role == "household.member"
            assert _count(conn, "app_users", "id=:uid", {"uid": users[1]}) == 1
            assert _count(conn, "app_users", "id=:uid", {"uid": users[2]}) == 1
        checks.append("oldest_remaining_user_promoted_and_shared_data_preserved")
        checks.append("sole_household_and_only_its_data_deleted")
        checks.append("other_user_and_household_untouched")

    finally:
        engine.dispose()
        reset_postgresql_test_database()

    for check in checks:
        print("PASS", check)
    print("RESULT", len(checks), "/", len(checks), "checks passed")
    print("ACCOUNT_DELETION_HOUSEHOLD_RETENTION_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
