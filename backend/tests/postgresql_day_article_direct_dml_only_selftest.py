from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    ensure_day_article_schema,
    get_default_inventory_handling,
    record_direct_consumption,
)

HOUSEHOLD_ID = "postgresql-pr2m-day-article"
ARTICLE_ID = "postgresql-pr2m-day-article-item"
IDEMPOTENCY_KEY = "postgresql-pr2m-direct-consumption"


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
            conn.execute(text("CREATE TABLE pr2m_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_DAY_ARTICLE_DIRECT_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a PR2m schema object")


def _assert_schema_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        ensure_day_article_schema(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Day-article schema validation unexpectedly mutated runtime schema")
    if "day_article_processing_events" not in after_tables:
        raise AssertionError("Alembic head mist day_article_processing_events")
    application_tables = after_tables - {"alembic_version"}
    print(
        "POSTGRESQL_DAY_ARTICLE_DIRECT_SCHEMA_VALIDATION_ONLY_GREEN "
        f"application_tables={len(application_tables)}"
    )


def _cleanup(conn) -> None:
    locations = conn.execute(
        text(
            """
            SELECT DISTINCT space_id, sublocation_id
            FROM day_article_processing_events
            WHERE household_id = :household_id
            """
        ),
        {"household_id": HOUSEHOLD_ID},
    ).mappings().all()
    conn.execute(
        text("DELETE FROM day_article_processing_events WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text("DELETE FROM household_articles WHERE id = :article_id"),
        {"article_id": ARTICLE_ID},
    )
    for row in locations:
        sublocation_id = str(row.get("sublocation_id") or "")
        space_id = str(row.get("space_id") or "")
        if sublocation_id:
            conn.execute(
                text("DELETE FROM sublocations WHERE id = :id"),
                {"id": sublocation_id},
            )
        if space_id:
            conn.execute(text("DELETE FROM spaces WHERE id = :id"), {"id": space_id})


def _seed_article(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_articles (
                id,
                household_id,
                naam,
                consumable,
                updated_at
            ) VALUES (
                :id,
                :household_id,
                'PR2m Dagartikel',
                1,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(id) DO UPDATE SET
                household_id = excluded.household_id,
                naam = excluded.naam,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"id": ARTICLE_ID, "household_id": HOUSEHOLD_ID},
    )


def _assert_direct_consumption_dml_only(engine) -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        _seed_article(conn)

        default = get_default_inventory_handling(conn, HOUSEHOLD_ID, ARTICLE_ID)
        if default["default_inventory_handling"] != "STOCK":
            raise AssertionError(default)

        first = record_direct_consumption(
            conn,
            household_id=HOUSEHOLD_ID,
            household_article_id=ARTICLE_ID,
            quantity="2.5",
            idempotency_key=IDEMPOTENCY_KEY,
            actor_user_id="postgresql-pr2m-actor",
        )
        if first["handling"] != DIRECT_CONSUMPTION or first["idempotent_replay"]:
            raise AssertionError(first)

        replay = record_direct_consumption(
            conn,
            household_id=HOUSEHOLD_ID,
            household_article_id=ARTICLE_ID,
            quantity="2.5",
            idempotency_key=IDEMPOTENCY_KEY,
            actor_user_id="postgresql-pr2m-actor",
        )
        if not replay["idempotent_replay"]:
            raise AssertionError(replay)

        events = conn.execute(
            text(
                """
                SELECT event_type, quantity, created_at
                FROM day_article_processing_events
                WHERE household_id = :household_id
                  AND idempotency_key = :idempotency_key
                ORDER BY event_type
                """
            ),
            {"household_id": HOUSEHOLD_ID, "idempotency_key": IDEMPOTENCY_KEY},
        ).mappings().all()
        if {str(row["event_type"]) for row in events} != {"RECEIPT", "DIRECT_CONSUMPTION"}:
            raise AssertionError(events)
        if len(events) != 2:
            raise AssertionError(events)
        for row in events:
            created_at = row["created_at"]
            if not isinstance(created_at, datetime) or created_at.tzinfo is None:
                raise AssertionError(f"Expected TIMESTAMPTZ value, got {created_at!r}")

        location = conn.execute(
            text(
                """
                SELECT s.protected AS space_protected,
                       sl.protected AS sublocation_protected
                FROM spaces s
                JOIN sublocations sl ON sl.space_id = s.id
                WHERE s.id = :space_id
                  AND sl.id = :sublocation_id
                """
            ),
            {
                "space_id": first["space_id"],
                "sublocation_id": first["sublocation_id"],
            },
        ).mappings().one()
        if location["space_protected"] is not True:
            raise AssertionError(location)
        if location["sublocation_protected"] is not True:
            raise AssertionError(location)

        _cleanup(conn)

    print("POSTGRESQL_DAY_ARTICLE_DIRECT_CONSUMPTION_DML_ONLY_GREEN")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_BOOLEAN_TIMESTAMP_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_only(engine)
        _assert_direct_consumption_dml_only(engine)
    finally:
        engine.dispose()
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_DML_ONLY_GREEN")
    print("POSTGRESQL_DAY_ARTICLE_DIRECT_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
