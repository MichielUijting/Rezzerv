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

from app.services.household_invitation_delivery_service import (
    InvitationEmailConfiguration,
    deliver_created_household_invitation,
    ensure_household_invitation_delivery_foundation,
    get_household_invitation_with_delivery,
)
from app.services.household_invitation_service import (
    InvitationConflictError,
    create_household_invitation,
    ensure_household_invitation_foundation,
    list_household_invitations,
    resolve_pending_invitation_token,
    revoke_household_invitation,
)

HOUSEHOLD_ID = "postgresql-pr2m-invitation"
ACTOR_USER_ID = "postgresql-pr2m-admin"
INVITEE_EMAIL = "postgresql-pr2m-invitee@example.com"


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
            conn.execute(text("CREATE TABLE invitation_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_HOUSEHOLD_INVITATION_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created an invitation schema object")


def _assert_schema_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        ensure_household_invitation_foundation(conn)
        ensure_household_invitation_delivery_foundation(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Invitation schema validation unexpectedly mutated runtime schema")
    if "household_invitations" not in after_tables:
        raise AssertionError("Alembic head is missing household_invitations")

    columns = {
        str(column["name"]): column
        for column in inspect(engine).get_columns("household_invitations")
    }
    for column_name in (
        "expires_at",
        "created_at",
        "updated_at",
        "accepted_at",
        "revoked_at",
        "last_delivery_attempt_at",
        "last_delivered_at",
    ):
        column_type = columns[column_name]["type"]
        if not isinstance(column_type, sa.DateTime) or not bool(
            getattr(column_type, "timezone", False)
        ):
            raise AssertionError(
                f"Expected TIMESTAMPTZ for household_invitations.{column_name}, got {column_type}"
            )
    application_tables = after_tables - {"alembic_version"}
    print(
        "POSTGRESQL_HOUSEHOLD_INVITATION_SCHEMA_VALIDATION_ONLY_GREEN "
        f"application_tables={len(application_tables)}"
    )


def _cleanup(conn) -> None:
    conn.execute(
        text("DELETE FROM household_invitations WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text("DELETE FROM auth_audit_log WHERE household_id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )
    conn.execute(
        text("DELETE FROM household_registry WHERE id = :household_id"),
        {"household_id": HOUSEHOLD_ID},
    )


def _seed_household(conn) -> None:
    _cleanup(conn)
    conn.execute(
        text(
            """
            INSERT INTO household_registry(id, naam, context_type)
            VALUES (:household_id, 'PostgreSQL invitation proof', 'regular')
            """
        ),
        {"household_id": HOUSEHOLD_ID},
    )


def _assert_request_dml_only(engine) -> None:
    disabled_email = InvitationEmailConfiguration(
        enabled=False,
        api_key="",
        api_base_url="https://api.resend.example",
        from_email="uitnodigingen@inhu.is",
        from_name="Inhuis",
        app_base_url="https://app.inhu.is",
    )

    with engine.begin() as conn:
        _seed_household(conn)
        result = create_household_invitation(
            conn,
            household_id=HOUSEHOLD_ID,
            invitee_email=INVITEE_EMAIL,
            created_by_user_id=ACTOR_USER_ID,
        )
        invitation_id = str(result.invitation["id"])
        if result.invitation["status"] != "pending":
            raise AssertionError(result.invitation)

        try:
            create_household_invitation(
                conn,
                household_id=HOUSEHOLD_ID,
                invitee_email=INVITEE_EMAIL,
                created_by_user_id=ACTOR_USER_ID,
            )
        except InvitationConflictError:
            pass
        else:
            raise AssertionError("Duplicate pending invitation unexpectedly succeeded")

        resolved = resolve_pending_invitation_token(conn, raw_token=result.raw_token)
        if str(resolved["id"]) != invitation_id:
            raise AssertionError(resolved)
        listed = list_household_invitations(conn, household_id=HOUSEHOLD_ID)
        if [str(item["id"]) for item in listed] != [invitation_id]:
            raise AssertionError(listed)
        print("POSTGRESQL_HOUSEHOLD_INVITATION_LIFECYCLE_DML_ONLY_GREEN")

        delivery = deliver_created_household_invitation(
            conn,
            household_id=HOUSEHOLD_ID,
            invitation_id=invitation_id,
            raw_token=result.raw_token,
            actor_user_id=ACTOR_USER_ID,
            configuration=disabled_email,
        )
        if delivery.status != "disabled":
            raise AssertionError(delivery)
        enriched = get_household_invitation_with_delivery(
            conn,
            household_id=HOUSEHOLD_ID,
            invitation_id=invitation_id,
        )
        if enriched["delivery_status"] != "disabled":
            raise AssertionError(enriched)
        if int(enriched["delivery_attempt_count"]) != 1:
            raise AssertionError(enriched)
        print("POSTGRESQL_HOUSEHOLD_INVITATION_DELIVERY_DML_ONLY_GREEN")

        revoked = revoke_household_invitation(
            conn,
            household_id=HOUSEHOLD_ID,
            invitation_id=invitation_id,
            actor_user_id=ACTOR_USER_ID,
        )
        if revoked["status"] != "revoked":
            raise AssertionError(revoked)
        _cleanup(conn)
        print("POSTGRESQL_HOUSEHOLD_INVITATION_REVOKE_DML_ONLY_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_only(engine)
        _assert_request_dml_only(engine)
    finally:
        engine.dispose()
    print("POSTGRESQL_HOUSEHOLD_INVITATION_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
