from __future__ import annotations

import uuid

from sqlalchemy import text

from app.services.multi_household_lifecycle_service import (
    HouseholdLifecycleConflictError,
    create_additional_household,
    delete_additional_household,
    household_deletion_eligibility,
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
from app.testing.onboarding_request_schema_fixture import (
    backfill_completed_household_onboarding,
)


def _expect_conflict(fn) -> None:
    try:
        fn()
    except HouseholdLifecycleConflictError:
        return
    raise AssertionError("verwacht HouseholdLifecycleConflictError")


def run() -> int:
    checks: list[str] = []
    snapshot = postgresql_acceptance_snapshot()
    assert snapshot["datastore"] == "postgresql"
    assert snapshot["runtime_create"] is False
    checks.append("postgresql_dml_only_runtime")

    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        user_id = f"user-{uuid.uuid4().hex}"
        email = f"{user_id}@example.test"
        initial_household = f"home-{uuid.uuid4().hex}"
        initial_membership = f"membership-{uuid.uuid4().hex}"

        with engine.begin() as conn:
            seed_household(
                conn,
                household_id=initial_household,
                name="Eerste huishouden",
            )
            seed_user(
                conn,
                user_id=user_id,
                email=email,
                password="KeepExistingLogin123!",
            )
            seed_membership(
                conn,
                membership_id=initial_membership,
                household_id=initial_household,
                user_id=user_id,
                email=email,
                role="admin",
            )
            backfill_completed_household_onboarding(conn)

            created = create_additional_household(
                conn,
                user_id=user_id,
                email=email,
                household_name="Nieuwe woning",
            )
            second_household = created["household_id"]
            second_membership = created["membership_id"]

            assert created["role"] == "admin"
            assert created["onboarding_status"] == "not_started"

            role = conn.execute(
                text(
                    """
                    SELECT role_key FROM auth_membership_roles
                    WHERE household_id=:household_id
                      AND membership_id=:membership_id
                      AND active IS TRUE
                    """
                ),
                {
                    "household_id": second_household,
                    "membership_id": second_membership,
                },
            ).scalar_one()
            assert role == "household.admin"

            onboarding = conn.execute(
                text(
                    """
                    SELECT onboarding_status, primary_use_case, onboarding_step
                    FROM household_onboarding
                    WHERE household_id=:household_id
                    """
                ),
                {"household_id": second_household},
            ).mappings().one()
            assert onboarding["onboarding_status"] == "not_started"
            assert onboarding["primary_use_case"] is None
            assert onboarding["onboarding_step"] == "primary_use_case"

            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": initial_household},
            ).scalar_one() == 1
        checks.append("additional_household_created_as_admin_with_fresh_onboarding")

        with engine.begin() as conn:
            eligible = household_deletion_eligibility(
                conn,
                household_id=second_household,
                user_id=user_id,
                active_household_id=initial_household,
            )
            assert eligible["can_delete"] is True
            assert eligible["reason"] == "sole_admin"

            other_user = f"user-{uuid.uuid4().hex}"
            other_email = f"{other_user}@example.test"
            other_membership = f"membership-{uuid.uuid4().hex}"
            seed_user(
                conn,
                user_id=other_user,
                email=other_email,
                password="TemporaryMember123!",
            )
            seed_membership(
                conn,
                membership_id=other_membership,
                household_id=second_household,
                user_id=other_user,
                email=other_email,
                role="member",
            )

            blocked = household_deletion_eligibility(
                conn,
                household_id=second_household,
                user_id=user_id,
                active_household_id=initial_household,
            )
            assert blocked["can_delete"] is False
            assert blocked["reason"] == "other_members"
            assert int(blocked["member_count"]) == 2

            _expect_conflict(
                lambda: delete_additional_household(
                    conn,
                    household_id=second_household,
                    user_id=user_id,
                    active_household_id=initial_household,
                    confirmation=f"VERWIJDER {second_household}",
                )
            )
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": second_household},
            ).scalar_one() == 1

            conn.execute(
                text(
                    """
                    DELETE FROM auth_membership_roles
                    WHERE household_id=:household_id AND membership_id=:membership_id
                    """
                ),
                {
                    "household_id": second_household,
                    "membership_id": other_membership,
                },
            )
            conn.execute(
                text(
                    """
                    DELETE FROM household_memberships
                    WHERE household_id=:household_id AND id=:membership_id
                    """
                ),
                {
                    "household_id": second_household,
                    "membership_id": other_membership,
                },
            )
            conn.execute(
                text("DELETE FROM app_users WHERE id=:user_id"),
                {"user_id": other_user},
            )
        checks.append("household_with_other_member_cannot_be_deleted")

        with engine.begin() as conn:
            space_id = f"space-{uuid.uuid4().hex}"
            sublocation_id = f"sublocation-{uuid.uuid4().hex}"
            conn.execute(
                text(
                    """
                    INSERT INTO spaces(id, naam, household_id, active)
                    VALUES (:id, 'Nieuwe woning', :household_id, TRUE)
                    """
                ),
                {"id": space_id, "household_id": second_household},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO sublocations(id, naam, space_id, active)
                    VALUES (:id, 'Kast', :space_id, TRUE)
                    """
                ),
                {"id": sublocation_id, "space_id": space_id},
            )

            _expect_conflict(
                lambda: delete_additional_household(
                    conn,
                    household_id=second_household,
                    user_id=user_id,
                    active_household_id=initial_household,
                    confirmation="VERWIJDER verkeerd",
                )
            )
            deleted = delete_additional_household(
                conn,
                household_id=second_household,
                user_id=user_id,
                active_household_id=initial_household,
                confirmation=f"VERWIJDER {second_household}",
            )
            assert deleted["deleted"] is True
            assert deleted["household_id"] == second_household

            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": second_household},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_memberships WHERE household_id=:id"),
                {"id": second_household},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM auth_membership_roles WHERE household_id=:id"),
                {"id": second_household},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_onboarding WHERE household_id=:id"),
                {"id": second_household},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id=:id"),
                {"id": second_household},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT COUNT(*) FROM sublocations WHERE id=:id"),
                {"id": sublocation_id},
            ).scalar_one() == 0

            account = conn.execute(
                text("SELECT email, password FROM app_users WHERE id=:user_id"),
                {"user_id": user_id},
            ).mappings().one()
            assert account["email"] == email
            assert account["password"] == "KeepExistingLogin123!"
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": initial_household},
            ).scalar_one() == 1
            assert conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM household_memberships
                    WHERE household_id=:household_id AND id=:membership_id
                    """
                ),
                {
                    "household_id": initial_household,
                    "membership_id": initial_membership,
                },
            ).scalar_one() == 1
        checks.append("sole_admin_can_delete_nonactive_household_without_losing_account_or_other_household")

        with engine.begin() as conn:
            third = create_additional_household(
                conn,
                user_id=user_id,
                email=email,
                household_name="Actief testhuishouden",
            )
            third_household = third["household_id"]
            _expect_conflict(
                lambda: delete_additional_household(
                    conn,
                    household_id=third_household,
                    user_id=user_id,
                    active_household_id=third_household,
                    confirmation=f"VERWIJDER {third_household}",
                )
            )
            assert conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id=:id"),
                {"id": third_household},
            ).scalar_one() == 1
        checks.append("active_household_must_be_switched_away_before_delete")

    finally:
        engine.dispose()
        reset_postgresql_test_database()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("MULTI_HOUSEHOLD_LIFECYCLE_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
