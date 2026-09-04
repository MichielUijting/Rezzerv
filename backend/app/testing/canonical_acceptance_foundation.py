"""Canonical PostgreSQL foundation for Rezzerv integral acceptance tests.

This module is test infrastructure only. It deliberately reuses the Alembic-owned
schema, the shared PostgreSQL acceptance boundary and existing onboarding seed
helpers. Schema creation/migration remains migrator authority; all scenario
seeding is performed through the DML-only runtime role.

The foundation provides three deterministic regular-household contexts:

- locations ON (`waar_inhuis`) with one real location and sublocation;
- locations OFF (`wat_inhuis`) with no locations;
- a second independent household for isolation assertions.

It fails closed for SQLite, for a runtime role with schema CREATE authority, for
schema-head drift, or when runtime and migrator resolve to the same database user.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from sqlalchemy import text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.household_location_onboarding_service import (
    ensure_location_foundation,
    provision_waar_inhuis_locations,
)
from app.services.household_onboarding_service import ensure_household_onboarding_foundation
from app.services.password_service import hash_password
from app.testing.onboarding_request_schema_fixture import backfill_completed_household_onboarding
from app.testing.postgresql_acceptance_foundation import (
    create_postgresql_runtime_test_engine,
    postgresql_acceptance_snapshot,
    reset_postgresql_test_database,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    seed_household,
    seed_user_membership,
)

TEST_PASSWORD_ENV = "REZZERV_ACCEPTANCE_TEST_PASSWORD"

LOCATIONS_ON_HOUSEHOLD_ID = "acceptance-locations-on"
LOCATIONS_OFF_HOUSEHOLD_ID = "acceptance-locations-off"
ISOLATION_HOUSEHOLD_ID = "acceptance-isolation"


@dataclass(frozen=True)
class AcceptanceActor:
    user_id: str
    email: str
    membership_id: str
    role: str


@dataclass(frozen=True)
class AcceptanceHousehold:
    household_id: str
    name: str
    primary_use_case: str
    locations_enabled: bool
    admin: AcceptanceActor
    member: AcceptanceActor


CANONICAL_HOUSEHOLDS = (
    AcceptanceHousehold(
        household_id=LOCATIONS_ON_HOUSEHOLD_ID,
        name="Acceptance locaties aan",
        primary_use_case="waar_inhuis",
        locations_enabled=True,
        admin=AcceptanceActor(
            user_id="acceptance-locations-on-admin",
            email="acceptance.locations.on.admin@example.test",
            membership_id="acceptance-locations-on-admin-membership",
            role="admin",
        ),
        member=AcceptanceActor(
            user_id="acceptance-locations-on-member",
            email="acceptance.locations.on.member@example.test",
            membership_id="acceptance-locations-on-member-membership",
            role="member",
        ),
    ),
    AcceptanceHousehold(
        household_id=LOCATIONS_OFF_HOUSEHOLD_ID,
        name="Acceptance locaties uit",
        primary_use_case="wat_inhuis",
        locations_enabled=False,
        admin=AcceptanceActor(
            user_id="acceptance-locations-off-admin",
            email="acceptance.locations.off.admin@example.test",
            membership_id="acceptance-locations-off-admin-membership",
            role="admin",
        ),
        member=AcceptanceActor(
            user_id="acceptance-locations-off-member",
            email="acceptance.locations.off.member@example.test",
            membership_id="acceptance-locations-off-member-membership",
            role="member",
        ),
    ),
    AcceptanceHousehold(
        household_id=ISOLATION_HOUSEHOLD_ID,
        name="Acceptance isolatie",
        primary_use_case="wat_inhuis",
        locations_enabled=False,
        admin=AcceptanceActor(
            user_id="acceptance-isolation-admin",
            email="acceptance.isolation.admin@example.test",
            membership_id="acceptance-isolation-admin-membership",
            role="admin",
        ),
        member=AcceptanceActor(
            user_id="acceptance-isolation-member",
            email="acceptance.isolation.member@example.test",
            membership_id="acceptance-isolation-member-membership",
            role="member",
        ),
    ),
)


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} ontbreekt voor canonical acceptance foundation")
    return value


def _set_completed_use_case(conn, household: AcceptanceHousehold) -> None:
    conn.execute(
        text(
            """
            UPDATE household_onboarding
            SET onboarding_status = 'completed',
                onboarding_version = 2,
                primary_use_case = :primary_use_case,
                onboarding_step = NULL,
                household_usage_mode = 'together',
                onboarding_completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id
            """
        ),
        {
            "household_id": household.household_id,
            "primary_use_case": household.primary_use_case,
        },
    )


def _seed_actor(conn, household: AcceptanceHousehold, actor: AcceptanceActor, password: str) -> None:
    seed_user_membership(
        conn,
        household_id=household.household_id,
        user_id=actor.user_id,
        email=actor.email,
        password=hash_password(password),
        membership_id=actor.membership_id,
        role=actor.role,
    )


def seed_canonical_acceptance_scenarios() -> dict[str, Any]:
    """Reset and seed canonical scenarios entirely through DML-authorized paths."""

    password = _required_env(TEST_PASSWORD_ENV)
    if len(password) < 16:
        raise RuntimeError(f"{TEST_PASSWORD_ENV} moet minimaal 16 tekens bevatten")

    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            ensure_authorization_foundation(conn)
            ensure_household_onboarding_foundation(conn)
            ensure_location_foundation(conn)

            for household in CANONICAL_HOUSEHOLDS:
                seed_household(
                    conn,
                    household_id=household.household_id,
                    name=household.name,
                    context_type="regular",
                )
                _seed_actor(conn, household, household.admin, password)
                _seed_actor(conn, household, household.member, password)

            backfill_completed_household_onboarding(conn)
            for household in CANONICAL_HOUSEHOLDS:
                _set_completed_use_case(conn, household)

            provisioned = provision_waar_inhuis_locations(
                conn,
                household_id=LOCATIONS_ON_HOUSEHOLD_ID,
                main_locations=["Voorraadkast"],
                sublocations=[
                    {"space_name": "Voorraadkast", "name": "Bovenste plank"}
                ],
            )

        return {
            "scenario_count": len(CANONICAL_HOUSEHOLDS),
            "household_ids": [item.household_id for item in CANONICAL_HOUSEHOLDS],
            "locations_on_space_id": provisioned["spaces"][0]["id"],
            "locations_on_sublocation_id": provisioned["sublocations"][0]["id"],
        }
    finally:
        engine.dispose()


def _scenario_snapshot() -> dict[str, Any]:
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.connect() as conn:
            onboarding_rows = conn.execute(
                text(
                    """
                    SELECT household_id, onboarding_status, primary_use_case
                    FROM household_onboarding
                    WHERE household_id IN (
                        :locations_on,
                        :locations_off,
                        :isolation
                    )
                    ORDER BY household_id
                    """
                ),
                {
                    "locations_on": LOCATIONS_ON_HOUSEHOLD_ID,
                    "locations_off": LOCATIONS_OFF_HOUSEHOLD_ID,
                    "isolation": ISOLATION_HOUSEHOLD_ID,
                },
            ).mappings().all()
            onboarding = {str(row["household_id"]): dict(row) for row in onboarding_rows}

            member_counts = {
                str(row["household_id"]): int(row["count"])
                for row in conn.execute(
                    text(
                        """
                        SELECT household_id, COUNT(*) AS count
                        FROM household_memberships
                        WHERE household_id IN (
                            :locations_on,
                            :locations_off,
                            :isolation
                        )
                        GROUP BY household_id
                        """
                    ),
                    {
                        "locations_on": LOCATIONS_ON_HOUSEHOLD_ID,
                        "locations_off": LOCATIONS_OFF_HOUSEHOLD_ID,
                        "isolation": ISOLATION_HOUSEHOLD_ID,
                    },
                ).mappings()
            }

            location_counts = {
                str(row["household_id"]): int(row["count"])
                for row in conn.execute(
                    text(
                        """
                        SELECT household_id, COUNT(*) AS count
                        FROM spaces
                        WHERE household_id IN (
                            :locations_on,
                            :locations_off,
                            :isolation
                        )
                        GROUP BY household_id
                        """
                    ),
                    {
                        "locations_on": LOCATIONS_ON_HOUSEHOLD_ID,
                        "locations_off": LOCATIONS_OFF_HOUSEHOLD_ID,
                        "isolation": ISOLATION_HOUSEHOLD_ID,
                    },
                ).mappings()
            }

            sublocation_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM sublocations sl
                        JOIN spaces s ON s.id = sl.space_id
                        WHERE s.household_id = :household_id
                        """
                    ),
                    {"household_id": LOCATIONS_ON_HOUSEHOLD_ID},
                ).scalar_one()
            )

        for household in CANONICAL_HOUSEHOLDS:
            row = onboarding.get(household.household_id)
            if not row:
                raise AssertionError(f"Onboarding ontbreekt voor {household.household_id}")
            if str(row.get("onboarding_status")) != "completed":
                raise AssertionError(f"Onboarding niet completed voor {household.household_id}")
            if str(row.get("primary_use_case")) != household.primary_use_case:
                raise AssertionError(f"Primary use case wijkt af voor {household.household_id}")
            if member_counts.get(household.household_id) != 2:
                raise AssertionError(f"Verwacht admin + member voor {household.household_id}")

        locations_on_spaces = location_counts.get(LOCATIONS_ON_HOUSEHOLD_ID, 0)
        locations_off_spaces = location_counts.get(LOCATIONS_OFF_HOUSEHOLD_ID, 0)
        isolation_spaces = location_counts.get(ISOLATION_HOUSEHOLD_ID, 0)
        if locations_on_spaces != 1 or sublocation_count != 1:
            raise AssertionError("Locaties-AAN scenario moet exact één space en sublocation hebben")
        if locations_off_spaces != 0:
            raise AssertionError("Locaties-UIT scenario mag geen spaces hebben")
        if isolation_spaces != 0:
            raise AssertionError("Isolation scenario mag geen locations-AAN data erven")

        return {
            "scenario_count": len(CANONICAL_HOUSEHOLDS),
            "locations_on_spaces": locations_on_spaces,
            "locations_on_sublocations": sublocation_count,
            "locations_off_spaces": locations_off_spaces,
            "isolation_spaces": isolation_spaces,
            "members_per_household": member_counts,
        }
    finally:
        engine.dispose()


def run_foundation_contract() -> dict[str, Any]:
    authority = postgresql_acceptance_snapshot()
    seed_result = seed_canonical_acceptance_scenarios()
    scenarios = _scenario_snapshot()
    candidate_sha = str(
        os.getenv("REZZERV_TEST_CANDIDATE_SHA")
        or os.getenv("GITHUB_SHA")
        or "local"
    ).strip()
    return {
        "candidate_sha": candidate_sha,
        **authority,
        **seed_result,
        **scenarios,
    }


def main() -> int:
    result = run_foundation_contract()
    print("REZZERV_CANONICAL_ACCEPTANCE_FOUNDATION")
    for key in (
        "candidate_sha",
        "datastore",
        "database",
        "alembic_head",
        "runtime_user",
        "migrator_user",
        "runtime_create",
        "migrator_create",
        "scenario_count",
        "locations_on_spaces",
        "locations_on_sublocations",
        "locations_off_spaces",
        "isolation_spaces",
    ):
        print(f"{key}={result[key]}")
    print("scenario_households=" + json.dumps(result["household_ids"], sort_keys=True))
    print("CANONICAL_ACCEPTANCE_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
