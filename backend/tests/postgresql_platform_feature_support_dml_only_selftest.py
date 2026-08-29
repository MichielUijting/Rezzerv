from __future__ import annotations

import os
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.platform_feature_flag_service import (
    FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
    ensure_platform_feature_flag_schema,
    get_platform_feature_flag,
    is_platform_feature_enabled,
    list_platform_feature_flags,
    set_platform_feature_flag,
)
from app.services.support_message_service import (
    RECIPIENT_SUPERUSER,
    STATUS_CLOSED,
    SupportMessageError,
    add_support_message,
    add_support_recipient,
    create_support_thread,
    ensure_support_message_foundation,
    list_support_messages,
    list_support_threads,
    set_support_thread_status,
)

HOUSEHOLD_ID = "postgresql-pr2n-support"
ADMIN_USER_ID = "postgresql-pr2n-admin"
SUPERUSER_ID = "postgresql-pr2n-superuser"


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
            conn.execute(text("CREATE TABLE platform_feature_support_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a platform feature/support schema object")


def _assert_schema_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        ensure_platform_feature_flag_schema(conn)
        ensure_support_message_foundation(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Platform feature/support validation unexpectedly mutated runtime schema")

    inspector = inspect(engine)
    feature_columns = {
        str(column["name"]): column
        for column in inspector.get_columns("platform_feature_flags")
    }
    if not isinstance(feature_columns["enabled"]["type"], sa.Boolean):
        raise AssertionError(feature_columns["enabled"])
    feature_updated_at = feature_columns["updated_at"]["type"]
    if not isinstance(feature_updated_at, sa.DateTime) or not bool(
        getattr(feature_updated_at, "timezone", False)
    ):
        raise AssertionError(feature_updated_at)

    support_columns = {
        table_name: {
            str(column["name"]): column
            for column in inspector.get_columns(table_name)
        }
        for table_name in ("support_threads", "support_messages", "support_recipients")
    }
    if not isinstance(support_columns["support_threads"]["reply_allowed"]["type"], sa.Boolean):
        raise AssertionError(support_columns["support_threads"]["reply_allowed"])
    for table_name, column_names in {
        "support_threads": ("created_at", "updated_at", "closed_at"),
        "support_messages": ("created_at",),
        "support_recipients": ("read_at", "created_at"),
    }.items():
        for column_name in column_names:
            column_type = support_columns[table_name][column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise AssertionError((table_name, column_name, column_type))

    print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_SCHEMA_VALIDATION_ONLY_GREEN")
    print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_TYPES_GREEN")


def _assert_feature_flag_dml(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM platform_feature_flags WHERE flag_key = :flag_key"),
            {"flag_key": FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH},
        )
        if not is_platform_feature_enabled(conn, FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH):
            raise AssertionError("Registered feature default should remain enabled without an override row")

        updated = set_platform_feature_flag(
            conn,
            FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH,
            enabled=False,
            updated_by=SUPERUSER_ID,
        )
        if updated["enabled"] is not False or updated["source"] != "override":
            raise AssertionError(updated)
        fetched = get_platform_feature_flag(conn, FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH)
        if fetched["enabled"] is not False:
            raise AssertionError(fetched)
        listed = {
            item["key"]: item
            for item in list_platform_feature_flags(conn)
        }
        if listed[FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH]["enabled"] is not False:
            raise AssertionError(listed)
        print("POSTGRESQL_PLATFORM_FEATURE_FLAG_DML_ONLY_GREEN")

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text("SET LOCAL search_path TO pg_catalog"))
            try:
                is_platform_feature_enabled(conn, FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH)
            except ProgrammingError:
                print("POSTGRESQL_PLATFORM_FEATURE_FLAG_SCHEMA_FAILURE_VISIBLE_GREEN")
            else:
                raise AssertionError("Feature-flag schema failure was unexpectedly masked by the rollout default")
        finally:
            transaction.rollback()


def _cleanup_support(conn) -> None:
    thread_ids = text(
        "SELECT id FROM support_threads WHERE household_id = :household_id"
    )
    conn.execute(
        text(
            "DELETE FROM support_recipients WHERE thread_id IN "
            "(SELECT id FROM support_threads WHERE household_id = :household_id)"
        ),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text(
            "DELETE FROM support_messages WHERE thread_id IN "
            "(SELECT id FROM support_threads WHERE household_id = :household_id)"
        ),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text("DELETE FROM support_threads WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )
    del thread_ids


def _assert_support_dml(engine) -> None:
    with engine.begin() as conn:
        _cleanup_support(conn)
        created = create_support_thread(
            conn,
            created_by_user_id=ADMIN_USER_ID,
            created_by_name="PostgreSQL admin",
            sender_role="admin",
            subject="PostgreSQL support authority proof",
            message_text="Eerste bericht",
            origin_screen_name="Instellingen",
            household_id=HOUSEHOLD_ID,
            recipient_type=RECIPIENT_SUPERUSER,
            reply_allowed=True,
            origin_route="/instellingen",
            origin_app_version="test",
        )
        add_support_recipient(
            conn,
            thread_id=created.thread_id,
            household_id=HOUSEHOLD_ID,
            admin_user_id=ADMIN_USER_ID,
        )
        add_support_recipient(
            conn,
            thread_id=created.thread_id,
            household_id=HOUSEHOLD_ID,
            admin_user_id=ADMIN_USER_ID,
        )
        recipient_count = int(
            conn.execute(
                text("SELECT COUNT(*) FROM support_recipients WHERE thread_id = :thread_id"),
                {"thread_id": created.thread_id},
            ).scalar_one()
        )
        if recipient_count != 1:
            raise AssertionError(recipient_count)

        add_support_message(
            conn,
            thread_id=created.thread_id,
            sender_user_id=ADMIN_USER_ID,
            sender_name="PostgreSQL admin",
            sender_role="admin",
            message_text="Tweede bericht",
            is_superuser=False,
            household_id=HOUSEHOLD_ID,
        )
        messages = list_support_messages(
            conn,
            thread_id=created.thread_id,
            household_id=HOUSEHOLD_ID,
            is_superuser=False,
        )
        if len(messages) != 2:
            raise AssertionError(messages)
        threads = list_support_threads(conn, household_id=HOUSEHOLD_ID)
        if not any(str(item["id"]) == created.thread_id for item in threads):
            raise AssertionError(threads)

        set_support_thread_status(conn, thread_id=created.thread_id, status=STATUS_CLOSED)
        closed = conn.execute(
            text("SELECT status, closed_at, reply_allowed FROM support_threads WHERE id = :id"),
            {"id": created.thread_id},
        ).mappings().one()
        if closed["status"] != STATUS_CLOSED or closed["closed_at"] is None:
            raise AssertionError(closed)
        if closed["reply_allowed"] is not True:
            raise AssertionError(closed)

        no_reply = create_support_thread(
            conn,
            created_by_user_id=ADMIN_USER_ID,
            created_by_name="PostgreSQL admin",
            sender_role="admin",
            subject="Geen antwoord toegestaan",
            message_text="Eerste bericht",
            origin_screen_name="Instellingen",
            household_id=HOUSEHOLD_ID,
            recipient_type=RECIPIENT_SUPERUSER,
            reply_allowed=False,
        )
        try:
            add_support_message(
                conn,
                thread_id=no_reply.thread_id,
                sender_user_id=ADMIN_USER_ID,
                sender_name="PostgreSQL admin",
                sender_role="admin",
                message_text="Dit antwoord moet worden geweigerd",
                is_superuser=False,
                household_id=HOUSEHOLD_ID,
            )
        except SupportMessageError:
            pass
        else:
            raise AssertionError("reply_allowed=False did not block a household reply")

        _cleanup_support(conn)
        print("POSTGRESQL_SUPPORT_PERSISTENCE_DML_ONLY_GREEN")
        print("POSTGRESQL_SUPPORT_REPLY_ALLOWED_BOOLEAN_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_only(engine)
        _assert_feature_flag_dml(engine)
        _assert_support_dml(engine)
    finally:
        engine.dispose()
    print("POSTGRESQL_PLATFORM_FEATURE_SUPPORT_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
