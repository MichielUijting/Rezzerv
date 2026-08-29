"""Self-contained validation for Onboarding v2 I.3 invitation email delivery."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re
import tempfile
import urllib.parse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.household_invitation_routes import create_household_invitation_router
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_invitation_delivery_service import (
    InvitationEmailConfiguration,
)
from app.services.household_invitation_service import (
    InvitationNotFoundError,
    create_household_invitation,
    hash_invitation_token,
    resolve_pending_invitation_token,
    utc_now,
)
from app.services.server_session_service import SESSION_COOKIE_NAME, create_server_session
from household_invitation_migrated_fixture import (
    insert_membership,
    insert_user,
    migrated_sqlite_engine,
)


class FakeResendTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.fail_next = False

    def __call__(self, payload: dict[str, object], _configuration: InvitationEmailConfiguration) -> str:
        self.payloads.append(dict(payload))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated provider outage")
        return f"resend-message-{len(self.payloads)}"


def _configuration(*, enabled: bool = True) -> InvitationEmailConfiguration:
    return InvitationEmailConfiguration(
        enabled=enabled,
        api_key="re_test_key",
        api_base_url="https://api.resend.example",
        from_email="uitnodigingen@inhu.is",
        from_name="Inhuis",
        app_base_url="https://app.inhu.is",
    )


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type) VALUES
                ('hh-a', 'Huis A', 'regular'),
                ('hh-b', 'Huis B', 'regular')
        """))
        for user_id, email in (
            ('admin-a', 'admin-a@example.com'),
            ('member-a', 'member-a@example.com'),
            ('admin-b', 'admin-b@example.com'),
            ('platform-target', 'platform-target@example.com'),
        ):
            insert_user(conn, user_id=user_id, email=email)
        for membership_id, household_id, user_id, email, role in (
            ('membership-admin-a', 'hh-a', 'admin-a', 'admin-a@example.com', 'admin'),
            ('membership-member-a', 'hh-a', 'member-a', 'member-a@example.com', 'member'),
            ('membership-admin-b', 'hh-b', 'admin-b', 'admin-b@example.com', 'admin'),
        ):
            insert_membership(
                conn,
                membership_id=membership_id,
                household_id=household_id,
                user_id=user_id,
                email=email,
                role=role,
            )
            create_canonical_membership_role(
                conn,
                household_id=household_id,
                membership_id=membership_id,
                legacy_role=role,
            )
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('platform-target', 'platform.frontteam', 1)
        """))


def _session(engine, user_id: str, household_id: str) -> str:
    with engine.begin() as conn:
        raw, _ = create_server_session(conn, user_id=user_id, active_household_id=household_id)
        return raw


def _client(app: FastAPI, raw_session: str) -> TestClient:
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, raw_session, domain="testserver.local", path="/")
    return client


def _application(engine, transport: FakeResendTransport, *, enabled: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_household_invitation_router(
            engine,
            email_configuration=_configuration(enabled=enabled),
            email_transport=transport,
        )
    )
    return app


def _token_from_payload(payload: dict[str, object]) -> str:
    body = str(payload.get("text") or "")
    match = re.search(r"https://app\.inhu\.is/uitnodiging/([^\s]+)", body)
    if not match:
        raise AssertionError("invitation link missing from outbound email")
    return urllib.parse.unquote(match.group(1))


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rezzerv-invitation-delivery-") as tmp:
        engine = migrated_sqlite_engine(
            Path(tmp) / 'delivery.db',
            check_same_thread=False,
        )
        _prepare_database(engine)
        transport = FakeResendTransport()
        app = _application(engine, transport)
        admin_a_session = _session(engine, "admin-a", "hh-a")
        member_a_session = _session(engine, "member-a", "hh-a")
        admin_b_session = _session(engine, "admin-b", "hh-b")

        with engine.begin() as conn:
            users_before = int(conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one())
            memberships_before = int(conn.execute(text("SELECT COUNT(*) FROM household_memberships")).scalar_one())

        with _client(app, admin_a_session) as admin:
            created = admin.post(
                "/api/household/invitations",
                json={"email": "invitee@example.com"},
            )
            assert created.status_code == 201, created.text
            body = created.json()
            invitation = body["invitation"]
            invitation_id = invitation["id"]
            assert body["delivery"]["status"] == "sent"
            assert invitation["delivery_status"] == "sent"
            assert invitation["delivery_attempt_count"] == 1
            assert invitation["delivery_provider_message_id"] == "resend-message-1"
            assert "raw_token" not in created.text
            assert "token_hash" not in created.text
        assert len(transport.payloads) == 1
        first_payload = transport.payloads[0]
        first_token = _token_from_payload(first_payload)
        assert first_token not in created.text
        assert first_payload["to"] == ["invitee@example.com"]
        assert "Huis A" in str(first_payload["subject"])
        assert "Rol: Lid" in str(first_payload["text"])
        assert "password" not in str(first_payload).lower()
        assert "tijdelijk wachtwoord" not in str(first_payload).lower()

        with engine.begin() as conn:
            row = conn.execute(text("""
                SELECT token_hash, delivery_status, delivery_attempt_count,
                       last_delivered_at, delivery_provider_message_id
                FROM household_invitations WHERE id = :id
            """), {"id": invitation_id}).mappings().one()
            assert row["token_hash"] == hash_invitation_token(first_token)
            assert row["token_hash"] != first_token
            assert row["delivery_status"] == "sent"
            assert int(row["delivery_attempt_count"]) == 1
            assert row["last_delivered_at"]
            assert row["delivery_provider_message_id"] == "resend-message-1"
            users_after = int(conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one())
            memberships_after = int(conn.execute(text("SELECT COUNT(*) FROM household_memberships")).scalar_one())
            assert users_after == users_before
            assert memberships_after == memberships_before
            audit_text = " ".join(str(value) for value in conn.execute(text("""
                SELECT new_value FROM auth_audit_log
                WHERE object_id = :id ORDER BY action
            """), {"id": invitation_id}).scalars().all())
            assert first_token not in audit_text
            assert "token_hash" not in audit_text
        checks.append("initial_delivery_sends_only_secure_acceptance_link_and_stores_hash_only")

        with _client(app, admin_a_session) as admin:
            resent = admin.post(f"/api/household/invitations/{invitation_id}/resend")
            assert resent.status_code == 200, resent.text
            resent_body = resent.json()
            assert resent_body["delivery"]["status"] == "sent"
            assert resent_body["invitation"]["delivery_attempt_count"] == 2
        second_token = _token_from_payload(transport.payloads[1])
        assert second_token != first_token
        with engine.begin() as conn:
            stored_hash = conn.execute(text(
                "SELECT token_hash FROM household_invitations WHERE id = :id"
            ), {"id": invitation_id}).scalar_one()
            assert stored_hash == hash_invitation_token(second_token)
            try:
                resolve_pending_invitation_token(conn, raw_token=first_token)
            except InvitationNotFoundError:
                pass
            else:
                raise AssertionError("old token remained valid after successful resend")
            assert resolve_pending_invitation_token(conn, raw_token=second_token)["id"] == invitation_id
        checks.append("successful_resend_rotates_token_and_invalidates_previous_link")

        transport.fail_next = True
        with engine.begin() as conn:
            hash_before_failure = conn.execute(text(
                "SELECT token_hash FROM household_invitations WHERE id = :id"
            ), {"id": invitation_id}).scalar_one()
        with _client(app, admin_a_session) as admin:
            failed = admin.post(f"/api/household/invitations/{invitation_id}/resend")
            assert failed.status_code == 502, failed.text
            assert failed.json()["detail"]["delivery"]["status"] == "failed"
        with engine.begin() as conn:
            failed_row = conn.execute(text("""
                SELECT token_hash, delivery_status, delivery_attempt_count,
                       last_delivered_at, delivery_provider_message_id, last_delivery_error
                FROM household_invitations WHERE id = :id
            """), {"id": invitation_id}).mappings().one()
            assert failed_row["token_hash"] == hash_before_failure
            assert failed_row["delivery_status"] == "failed"
            assert int(failed_row["delivery_attempt_count"]) == 3
            assert failed_row["last_delivered_at"]
            assert failed_row["delivery_provider_message_id"] == "resend-message-2"
            assert failed_row["last_delivery_error"]
            assert resolve_pending_invitation_token(conn, raw_token=second_token)["id"] == invitation_id
        checks.append("failed_resend_records_failure_without_invalidating_last_delivered_link")

        disabled_transport_count = len(transport.payloads)
        disabled_app = _application(engine, transport, enabled=False)
        with _client(disabled_app, admin_a_session) as admin:
            disabled = admin.post(
                "/api/household/invitations",
                json={"email": "disabled-delivery@example.com"},
            )
            assert disabled.status_code == 201, disabled.text
            disabled_body = disabled.json()
            assert disabled_body["delivery"]["status"] == "disabled"
            assert disabled_body["invitation"]["status"] == "pending"
            assert disabled_body["invitation"]["delivery_status"] == "disabled"
        assert len(transport.payloads) == disabled_transport_count
        checks.append("delivery_configuration_failure_does_not_destroy_pending_invitation")

        with _client(app, member_a_session) as member:
            denied = member.post(f"/api/household/invitations/{invitation_id}/resend")
            assert denied.status_code == 403, denied.text
            assert denied.json()["detail"]["permission_key"] == "members.manage"
        checks.append("resend_requires_canonical_members_manage")

        with _client(app, admin_b_session) as admin_b:
            created_b = admin_b.post(
                "/api/household/invitations",
                json={"email": "other-household@example.com"},
            )
            assert created_b.status_code == 201, created_b.text
            invitation_b_id = created_b.json()["invitation"]["id"]
        with _client(app, admin_a_session) as admin_a:
            cross = admin_a.post(f"/api/household/invitations/{invitation_b_id}/resend")
            assert cross.status_code == 404, cross.text
        checks.append("resend_is_scoped_to_authoritative_session_household")

        with engine.begin() as conn:
            platform_result = create_household_invitation(
                conn,
                household_id="hh-a",
                invitee_email="platform-target@example.com",
                created_by_user_id="admin-a",
            )
            platform_invitation_id = str(platform_result.invitation["id"])
        with _client(app, admin_a_session) as admin:
            platform_resend = admin.post(
                f"/api/household/invitations/{platform_invitation_id}/resend"
            )
            assert platform_resend.status_code == 409, platform_resend.text
        checks.append("resend_rechecks_platform_target_policy")

        old_now = utc_now() - timedelta(days=8)
        with engine.begin() as conn:
            expired_result = create_household_invitation(
                conn,
                household_id="hh-a",
                invitee_email="expired-delivery@example.com",
                created_by_user_id="admin-a",
                now=old_now,
            )
            expired_id = str(expired_result.invitation["id"])
        with _client(app, admin_a_session) as admin:
            expired = admin.post(f"/api/household/invitations/{expired_id}/resend")
            assert expired.status_code == 409, expired.text
            revoked = admin.post(f"/api/household/invitations/{invitation_id}/revoke")
            assert revoked.status_code == 200, revoked.text
            after_revoke = admin.post(f"/api/household/invitations/{invitation_id}/resend")
            assert after_revoke.status_code == 409, after_revoke.text
        checks.append("expired_or_revoked_invitations_cannot_be_resent")

        with engine.begin() as conn:
            audit_values = conn.execute(text("""
                SELECT action, new_value FROM auth_audit_log
                WHERE action IN ('household.invitation.delivery_attempted', 'household.invitation.token_rotated')
                ORDER BY action
            """)).mappings().all()
            assert audit_values
            serialized = " ".join(str(row) for row in audit_values)
            for payload in transport.payloads:
                token = _token_from_payload(payload)
                assert token not in serialized
            assert "token_hash" not in serialized
        checks.append("delivery_and_rotation_audit_never_contains_bearer_token_material")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("HOUSEHOLD_INVITATION_DELIVERY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
