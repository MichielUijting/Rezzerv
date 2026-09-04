"""P0 F3-02: onboarding -> invitation -> membership API authority on PostgreSQL.

This closes the gap between the existing strong service-oriented onboarding and
invitation tests and a production-like API authority. Account registration,
login, invitation creation, invitation acceptance and household switching all
run through real HTTP routes with opaque server-session cookies. Business,
authorization and persistence services are not mocked; only the outbound email
transport is captured so the one-time acceptance token can be exercised.
"""

from __future__ import annotations

import re
import urllib.parse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.household_invitation_acceptance_routes import (
    create_household_invitation_acceptance_router,
)
from app.api.household_invitation_routes import create_household_invitation_router
from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.api.session_household_routes import create_session_household_router
from app.services.household_invitation_delivery_service import InvitationEmailConfiguration
from app.services.household_invitation_service import hash_invitation_token
from app.services.server_session_service import SESSION_COOKIE_NAME
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

TARGET_HOUSEHOLD = "f3-membership-target"
ISOLATION_HOUSEHOLD = "f3-membership-isolation"
TARGET_ADMIN_EMAIL = "f3-target-admin@rezzerv.local"
TARGET_MEMBER_EMAIL = "f3-target-member@rezzerv.local"
ISOLATION_ADMIN_EMAIL = "f3-isolation-admin@rezzerv.local"
INVITEE_EMAIL = "f3-new-consumer@example.com"
SEED_PASSWORD = "F3MembershipSeed123!"
INVITEE_PASSWORD = "F3MembershipConsumer123!"


class CaptureInvitationTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def __call__(
        self,
        payload: dict[str, object],
        _configuration: InvitationEmailConfiguration,
    ) -> str:
        self.payloads.append(dict(payload))
        return f"f3-membership-message-{len(self.payloads)}"


def _email_configuration() -> InvitationEmailConfiguration:
    return InvitationEmailConfiguration(
        enabled=True,
        api_key="f3_test_key",
        api_base_url="https://api.resend.example",
        from_email="uitnodigingen@inhu.is",
        from_name="Inhuis",
        app_base_url="https://app.inhu.is",
    )


def _token_from_payload(payload: dict[str, object]) -> str:
    text_body = str(payload.get("text") or "")
    match = re.search(r"https://app\.inhu\.is/uitnodiging/([^\s]+)", text_body)
    if not match:
        raise AssertionError("acceptance token ontbreekt in afgevangen uitnodigingsmail")
    return urllib.parse.unquote(match.group(1))


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id=TARGET_HOUSEHOLD,
        household_name="F3 doelhuishouden",
        admin_id="f3-target-admin",
        admin_email=TARGET_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-target-admin-membership",
        member_id="f3-target-member",
        member_email=TARGET_MEMBER_EMAIL,
        member_password=SEED_PASSWORD,
        member_membership_id="f3-target-member-membership",
    )
    seed_admin_member_household(
        engine,
        household_id=ISOLATION_HOUSEHOLD,
        household_name="F3 isolatiehuishouden",
        admin_id="f3-isolation-admin",
        admin_email=ISOLATION_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-isolation-admin-membership",
        member_id="f3-isolation-member",
        member_email="f3-isolation-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-isolation-member-membership",
    )


def _application(engine, transport: CaptureInvitationTransport) -> FastAPI:
    configuration = SessionApiConfiguration(cookie_secure=False, cookie_samesite="lax")
    app = FastAPI()
    app.include_router(create_server_session_router(engine, configuration))
    app.include_router(
        create_household_invitation_router(
            engine,
            email_configuration=_email_configuration(),
            email_transport=transport,
        )
    )
    app.include_router(create_household_invitation_acceptance_router(engine, configuration))
    app.include_router(create_session_household_router(engine, configuration))
    return app


def _login(client: TestClient, email: str, password: str = SEED_PASSWORD) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE_NAME)
    return response.json()


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            runtime_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )
            assert runtime_create is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)
        transport = CaptureInvitationTransport()
        app = _application(engine, transport)

        with TestClient(app) as invitee:
            registered = invitee.post(
                "/api/auth/register",
                json={"email": INVITEE_EMAIL, "password": INVITEE_PASSWORD},
            )
            assert registered.status_code == 201, registered.text
            registration_payload = registered.json()
            own_household_id = str(registration_payload["active_household_id"])
            assert own_household_id
            assert own_household_id not in {TARGET_HOUSEHOLD, ISOLATION_HOUSEHOLD, "0"}
            assert registration_payload["role"] == "admin"
            assert registration_payload["context_type"] == "regular"
            first_session_cookie = invitee.cookies.get(SESSION_COOKIE_NAME)
            assert first_session_cookie
            checks.append("consumer_registers_real_regular_household_via_api")

            with engine.begin() as conn:
                households_after_registration = int(
                    conn.execute(text("SELECT COUNT(*) FROM household_registry")).scalar_one()
                )
                invitee_user_id = str(
                    conn.execute(
                        text("SELECT id FROM app_users WHERE lower(email) = :email"),
                        {"email": INVITEE_EMAIL},
                    ).scalar_one()
                )
                own_membership = conn.execute(
                    text(
                        """
                        SELECT id, role
                        FROM household_memberships
                        WHERE household_id = :household_id
                          AND lower(user_email) = :email
                        """
                    ),
                    {"household_id": own_household_id, "email": INVITEE_EMAIL},
                ).mappings().one()
                assert own_membership["role"] == "admin"
                own_role = conn.execute(
                    text(
                        """
                        SELECT role_key
                        FROM auth_membership_roles
                        WHERE household_id = :household_id
                          AND membership_id = :membership_id
                          AND active IS TRUE
                        """
                    ),
                    {
                        "household_id": own_household_id,
                        "membership_id": str(own_membership["id"]),
                    },
                ).scalar_one()
                assert own_role == "household.admin"
            checks.append("registration_persists_canonical_admin_membership")

            with TestClient(app) as ordinary_member:
                member_login = _login(ordinary_member, TARGET_MEMBER_EMAIL)
                assert member_login["active_household_id"] == TARGET_HOUSEHOLD
                denied = ordinary_member.post(
                    "/api/household/invitations",
                    json={"email": "f3-denied@example.com"},
                )
                assert denied.status_code == 403, denied.text
                assert denied.json()["detail"]["permission_key"] == "members.manage"
            checks.append("ordinary_member_cannot_invite")

            with TestClient(app) as target_admin:
                admin_login = _login(target_admin, TARGET_ADMIN_EMAIL)
                assert admin_login["active_household_id"] == TARGET_HOUSEHOLD
                created = target_admin.post(
                    "/api/household/invitations",
                    json={"email": INVITEE_EMAIL},
                )
                assert created.status_code == 201, created.text
                created_payload = created.json()
                invitation_id = str(created_payload["invitation"]["id"])
                assert created_payload["delivery"]["status"] == "sent"
                assert "raw_token" not in created.text
                assert "token_hash" not in created.text
            assert len(transport.payloads) == 1
            raw_token = _token_from_payload(transport.payloads[0])
            assert raw_token not in created.text
            checks.append("admin_creates_token_redacted_invitation_via_api")

            preview = invitee.get(f"/api/household/invitations/accept/{raw_token}")
            assert preview.status_code == 200, preview.text
            preview_payload = preview.json()
            assert preview_payload["household_name"] == "F3 doelhuishouden"
            assert preview_payload["account_exists"] is True
            assert preview_payload["authenticated"] is True
            assert preview_payload["authenticated_email_matches"] is True
            assert "household_id" not in preview_payload
            assert "token_hash" not in preview_payload
            checks.append("logged_in_invitee_preview_is_token_bound_and_minimal")

            accepted = invitee.post(
                f"/api/household/invitations/accept/{raw_token}",
                json={},
            )
            assert accepted.status_code == 200, accepted.text
            accepted_payload = accepted.json()
            assert accepted_payload["invitation_accepted"] is True
            assert accepted_payload["active_household_id"] == TARGET_HOUSEHOLD
            assert accepted_payload["role"] == "member"
            rotated_after_accept = invitee.cookies.get(SESSION_COOKIE_NAME)
            assert rotated_after_accept
            assert rotated_after_accept != first_session_cookie

            current = invitee.get("/api/session")
            assert current.status_code == 200, current.text
            assert current.json()["active_household_id"] == TARGET_HOUSEHOLD
            assert current.json()["role"] == "member"
            checks.append("invitation_acceptance_rotates_real_session_to_target_household")

            households = invitee.get("/api/session/households")
            assert households.status_code == 200, households.text
            household_payload = households.json()
            assert household_payload["can_switch_households"] is True
            assert household_payload["total"] == 2
            items = {item["household_id"]: item for item in household_payload["items"]}
            assert set(items) == {own_household_id, TARGET_HOUSEHOLD}
            assert items[own_household_id]["role"] == "admin"
            assert items[TARGET_HOUSEHOLD]["role"] == "member"
            assert items[TARGET_HOUSEHOLD]["active"] is True

            switch_own = invitee.post(
                "/api/session/household",
                json={"household_id": own_household_id},
            )
            assert switch_own.status_code == 200, switch_own.text
            assert switch_own.json()["active_household_id"] == own_household_id
            assert switch_own.json()["role"] == "admin"

            cross_household = invitee.post(
                "/api/session/household",
                json={"household_id": ISOLATION_HOUSEHOLD},
            )
            assert cross_household.status_code == 403, cross_household.text
            after_forbidden = invitee.get("/api/session")
            assert after_forbidden.status_code == 200, after_forbidden.text
            assert after_forbidden.json()["active_household_id"] == own_household_id
            checks.append("household_switching_uses_membership_and_blocks_isolation_escape")

            with engine.begin() as conn:
                household_count_after_acceptance = int(
                    conn.execute(text("SELECT COUNT(*) FROM household_registry")).scalar_one()
                )
                assert household_count_after_acceptance == households_after_registration

                memberships = conn.execute(
                    text(
                        """
                        SELECT id, household_id, role
                        FROM household_memberships
                        WHERE lower(user_email) = :email
                        ORDER BY household_id
                        """
                    ),
                    {"email": INVITEE_EMAIL},
                ).mappings().all()
                assert len(memberships) == 2, memberships
                by_household = {str(row["household_id"]): row for row in memberships}
                assert set(by_household) == {own_household_id, TARGET_HOUSEHOLD}
                assert by_household[own_household_id]["role"] == "admin"
                assert by_household[TARGET_HOUSEHOLD]["role"] == "member"

                target_role = conn.execute(
                    text(
                        """
                        SELECT role_key
                        FROM auth_membership_roles
                        WHERE household_id = :household_id
                          AND membership_id = :membership_id
                          AND active IS TRUE
                        """
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "membership_id": str(by_household[TARGET_HOUSEHOLD]["id"]),
                    },
                ).scalar_one()
                assert target_role == "household.member"

                isolation_memberships = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM household_memberships
                            WHERE household_id = :household_id
                              AND lower(user_email) = :email
                            """
                        ),
                        {"household_id": ISOLATION_HOUSEHOLD, "email": INVITEE_EMAIL},
                    ).scalar_one()
                )
                assert isolation_memberships == 0

                invitation = conn.execute(
                    text(
                        """
                        SELECT household_id, invitee_email, status, accepted_by_user_id,
                               accepted_at, token_hash
                        FROM household_invitations
                        WHERE id = :invitation_id
                        """
                    ),
                    {"invitation_id": invitation_id},
                ).mappings().one()
                assert invitation["household_id"] == TARGET_HOUSEHOLD
                assert str(invitation["invitee_email"]).lower() == INVITEE_EMAIL
                assert invitation["status"] == "accepted"
                assert str(invitation["accepted_by_user_id"]) == invitee_user_id
                assert invitation["accepted_at"] is not None
                assert invitation["token_hash"] == hash_invitation_token(raw_token)
                assert invitation["token_hash"] != raw_token

                duplicate_target_memberships = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM household_memberships
                            WHERE household_id = :household_id
                              AND lower(user_email) = :email
                            """
                        ),
                        {"household_id": TARGET_HOUSEHOLD, "email": INVITEE_EMAIL},
                    ).scalar_one()
                )
                assert duplicate_target_memberships == 1
            checks.append("postgresql_end_state_has_exact_memberships_roles_and_accepted_invitation")

            replay = invitee.post(
                f"/api/household/invitations/accept/{raw_token}",
                json={},
            )
            assert replay.status_code == 409, replay.text
            assert replay.json()["detail"] == "Uitnodiging is niet meer geldig"
            with engine.begin() as conn:
                duplicate_after_replay = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM household_memberships
                            WHERE household_id = :household_id
                              AND lower(user_email) = :email
                            """
                        ),
                        {"household_id": TARGET_HOUSEHOLD, "email": INVITEE_EMAIL},
                    ).scalar_one()
                )
                assert duplicate_after_replay == 1
            checks.append("accepted_token_replay_cannot_duplicate_membership")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("ONBOARDING_HOUSEHOLD_MEMBERSHIP_API_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
