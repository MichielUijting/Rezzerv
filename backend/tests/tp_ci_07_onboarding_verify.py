#!/usr/bin/env python3
"""PostgreSQL authority checks for TP-CI-07 L4-01 onboarding.

This is a direct extraction of the boundary and end-state assertions from the
standalone P0 onboarding full-stack workflow so the shared runner can reuse the
same authority without embedding a second copy in YAML.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import text

from app.db import engine
from app.services.household_product_use_case_service import resolve_active_household_product_use_cases


EXPECTED_CONFIGURATION_COLUMNS = {
    "household_id",
    "inventory_tracking_level",
    "location_tracking_level",
    "almost_out_enabled",
    "shopping_enabled",
}


def _schema_snapshot(conn):
    current_database = str(conn.execute(text("SELECT current_database() ")).scalar_one())
    current_schema = str(conn.execute(text("SELECT current_schema() ")).scalar_one())
    search_path = str(conn.execute(text("SHOW search_path")).scalar_one())
    alembic_head = str(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one())
    registry_columns = [
        str(value)
        for value in conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'household_registry'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()
    ]
    configuration_columns = [
        str(value)
        for value in conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'household_product_configuration'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()
    ]
    configuration_relation = conn.execute(
        text(
            """
            SELECT n.nspname AS schema_name,
                   c.relname AS relation_name,
                   c.oid::text AS relation_oid
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'household_product_configuration'
            """
        )
    ).mappings().one()
    return {
        "current_database": current_database,
        "current_schema": current_schema,
        "search_path": search_path,
        "alembic_head": alembic_head,
        "registry_columns": registry_columns,
        "configuration_columns": configuration_columns,
        "configuration_relation": configuration_relation,
    }


def boundary() -> None:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        )
        snapshot = _schema_snapshot(conn)

    assert current_user == "rezzerv_app", current_user
    assert snapshot["current_schema"] == "public", snapshot["current_schema"]
    assert runtime_create is False
    assert snapshot["alembic_head"]
    assert "naam" in snapshot["registry_columns"], snapshot["registry_columns"]
    assert EXPECTED_CONFIGURATION_COLUMNS.issubset(set(snapshot["configuration_columns"])), snapshot[
        "configuration_columns"
    ]
    relation = snapshot["configuration_relation"]
    print("datastore=postgresql", flush=True)
    print(f"database={snapshot['current_database']}", flush=True)
    print(f"schema={snapshot['current_schema']}", flush=True)
    print(f"search_path={snapshot['search_path']}", flush=True)
    print(f"runtime_user={current_user}", flush=True)
    print(f"runtime_create={runtime_create}", flush=True)
    print(f"alembic_head={snapshot['alembic_head']}", flush=True)
    print(f"household_registry_columns={','.join(snapshot['registry_columns'])}", flush=True)
    print(
        "household_product_configuration_relation="
        f"{relation['schema_name']}.{relation['relation_name']}@{relation['relation_oid']}",
        flush=True,
    )
    print(
        f"household_product_configuration_columns={','.join(snapshot['configuration_columns'])}",
        flush=True,
    )
    print("P0_L4_01_POSTGRESQL_BOUNDARY_GREEN", flush=True)


def verify() -> None:
    email = os.environ["L4_EMAIL"].strip().lower()
    expected_household_name = os.environ["L4_HOUSEHOLD_NAME"].strip()

    with engine.begin() as conn:
        snapshot = _schema_snapshot(conn)
        current_schemas = [
            str(value)
            for value in conn.execute(text("SELECT unnest(current_schemas(true))")).scalars().all()
        ]
        assert snapshot["current_schema"] == "public", snapshot["current_schema"]
        assert "naam" in snapshot["registry_columns"], snapshot["registry_columns"]
        assert EXPECTED_CONFIGURATION_COLUMNS.issubset(set(snapshot["configuration_columns"])), snapshot[
            "configuration_columns"
        ]

        memberships = conn.execute(
            text(
                """
                SELECT hm.id AS membership_id, hm.household_id, hm.role, hr.naam AS household_name
                FROM public.household_memberships hm
                JOIN public.household_registry hr ON hr.id = hm.household_id
                WHERE lower(trim(hm.user_email)) = :email
                ORDER BY hm.household_id
                """
            ),
            {"email": email},
        ).mappings().all()
        assert len(memberships) == 1, memberships
        membership = memberships[0]
        household_id = str(membership["household_id"])
        assert str(membership["role"]) == "admin", membership
        assert str(membership["household_name"]) == expected_household_name, membership

        onboarding = conn.execute(
            text(
                """
                SELECT onboarding_status, primary_use_case, household_usage_mode,
                       onboarding_completed_at
                FROM public.household_onboarding
                WHERE household_id = :household_id
                """
            ),
            {"household_id": household_id},
        ).mappings().one()
        assert str(onboarding["onboarding_status"]) == "completed", onboarding
        assert str(onboarding["primary_use_case"]) == "wat_inhuis", onboarding
        assert str(onboarding["household_usage_mode"]) == "alone", onboarding
        assert onboarding["onboarding_completed_at"] is not None, onboarding

        configuration = conn.execute(
            text(
                """
                SELECT inventory_tracking_level, location_tracking_level,
                       almost_out_enabled, shopping_enabled
                FROM public.household_product_configuration
                WHERE household_id = :household_id
                """
            ),
            {"household_id": household_id},
        ).mappings().one()
        assert configuration["inventory_tracking_level"] == "quantity", configuration
        assert configuration["location_tracking_level"] == "none", configuration
        assert bool(configuration["almost_out_enabled"]) is True, configuration
        assert bool(configuration["shopping_enabled"]) is True, configuration

        additional_use_cases = [
            str(row["use_case"])
            for row in conn.execute(
                text(
                    """
                    SELECT use_case
                    FROM public.household_product_use_cases
                    WHERE household_id = :household_id
                    ORDER BY use_case
                    """
                ),
                {"household_id": household_id},
            ).mappings().all()
        ]
        assert additional_use_cases == [], additional_use_cases
        active_use_cases = resolve_active_household_product_use_cases(
            conn,
            household_id=household_id,
            primary_use_case=str(onboarding["primary_use_case"]),
        )
        assert active_use_cases == ["wat_inhuis"], active_use_cases

        location_count = int(
            conn.execute(
                text("SELECT COUNT(*) FROM public.spaces WHERE household_id = :household_id"),
                {"household_id": household_id},
            ).scalar_one()
        )
        assert location_count == 0, location_count

    relation = snapshot["configuration_relation"]
    print(f"database={snapshot['current_database']}", flush=True)
    print(f"schema={snapshot['current_schema']}", flush=True)
    print(f"search_path={snapshot['search_path']}", flush=True)
    print(f"current_schemas={','.join(current_schemas)}", flush=True)
    print(f"alembic_head={snapshot['alembic_head']}", flush=True)
    print(f"household_registry_columns={','.join(snapshot['registry_columns'])}", flush=True)
    print(
        "household_product_configuration_relation="
        f"{relation['schema_name']}.{relation['relation_name']}@{relation['relation_oid']}",
        flush=True,
    )
    print(
        f"household_product_configuration_columns={','.join(snapshot['configuration_columns'])}",
        flush=True,
    )
    print(f"email={email}", flush=True)
    print(f"household_id={household_id}", flush=True)
    print(f"household_name={expected_household_name}", flush=True)
    print("onboarding_status=completed", flush=True)
    print("primary_use_case=wat_inhuis", flush=True)
    print("household_usage_mode=alone", flush=True)
    print("inventory_tracking_level=quantity", flush=True)
    print("location_tracking_level=none", flush=True)
    print("almost_out_enabled=true", flush=True)
    print("shopping_enabled=true", flush=True)
    print("additional_use_cases=", flush=True)
    print("active_use_cases=wat_inhuis", flush=True)
    print("spaces=0", flush=True)
    print("P0_L4_01_POSTGRESQL_END_STATE_GREEN", flush=True)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"boundary", "verify"}:
        print("usage: tp_ci_07_onboarding_verify.py <boundary|verify>", file=sys.stderr)
        return 2
    if sys.argv[1] == "boundary":
        boundary()
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
