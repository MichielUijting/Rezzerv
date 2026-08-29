from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.household_capability_expansion_service import (
    expand_household_product_configuration,
)
from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
)
from app.services.household_product_use_case_service import (
    activate_household_product_use_case,
    ensure_household_product_use_case_foundation,
    resolve_active_household_product_use_cases,
)

HOUSEHOLD_ID = "postgresql-pr2k-onboarding-use-case"


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _assert_runtime_create_denied(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pr2k_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_ONBOARDING_USE_CASE_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a PR2k schema object")


def _assert_schema_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        ensure_household_product_configuration_foundation(conn)
        ensure_household_product_use_case_foundation(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("PR2k schema validation unexpectedly mutated runtime schema")
    if "household_product_use_cases" not in after_tables:
        raise AssertionError("Alembic head is missing household_product_use_cases")
    print("POSTGRESQL_ONBOARDING_USE_CASE_SCHEMA_VALIDATION_ONLY_GREEN")


def _cleanup(conn) -> None:
    conn.execute(
        text("DELETE FROM household_product_use_cases WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text("DELETE FROM household_product_configuration WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )


def _assert_request_dml_only(engine) -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        configuration = expand_household_product_configuration(
            conn,
            household_id=HOUSEHOLD_ID,
            inventory_tracking_level="presence",
            shopping_enabled=True,
        )
        if configuration.inventory_tracking_level != "presence":
            raise AssertionError(configuration)
        if not configuration.shopping_enabled:
            raise AssertionError(configuration)

        activate_household_product_use_case(
            conn,
            household_id=HOUSEHOLD_ID,
            use_case="wat_inhuis",
        )
        activate_household_product_use_case(
            conn,
            household_id=HOUSEHOLD_ID,
            use_case="waar_inhuis",
        )
        # Idempotency must use portable ON CONFLICT, not SQLite INSERT OR IGNORE.
        activate_household_product_use_case(
            conn,
            household_id=HOUSEHOLD_ID,
            use_case="wat_inhuis",
        )
        active = resolve_active_household_product_use_cases(
            conn,
            household_id=HOUSEHOLD_ID,
        )
        if active != ["wat_inhuis", "waar_inhuis"]:
            raise AssertionError(f"Unexpected active use cases: {active!r}")
        _cleanup(conn)

    print("POSTGRESQL_ONBOARDING_CAPABILITY_DML_ONLY_GREEN")
    print("POSTGRESQL_ONBOARDING_USE_CASE_DML_ONLY_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_only(engine)
        _assert_request_dml_only(engine)
    finally:
        engine.dispose()
    print("POSTGRESQL_ONBOARDING_USE_CASE_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
