"""Self-contained validation for Onboarding v2 I.2 invitation acceptance."""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.household_invitation_acceptance_routes import create_household_invitation_acceptance_router
from app.api.server_session_routes import SessionApiConfiguration
from app.api.session_household_routes import create_session_household_router
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_invitation_service import create_household_invitation
from app.services.password_service import hash_password
from app.services.server_session_service import SESSION_COOKIE_NAME, create_server_session
from household_invitation_migrated_fixture import insert_membership, migrated_sqlite_engine


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type) VALUES
                ('hh-own', 'Eigen huis', 'regular'),
                ('hh-invite', 'Samen thuis', 'regular'),
                ('hh-other', 'Ander huis', 'regular'),
                ('0', 'Systeem', 'system')
        """))
        for user_id, email, password in (
            ('existing-user', 'existing@example.com', 'ExistingPassword123'),
            ('wrong-user', 'wrong@example.com', 'WrongPassword123'),
            ('invite-admin', 'invite-admin@example.com', 'InviteAdmin123'),
        ):
            encoded = hash_password(password)
            conn.execute(text("""
                INSERT INTO app_users(id, email, password, password_hash, account_status)
                VALUES (:id, :email, :password, :password_hash, 'active')
            """), {'id': user_id, 'email': email, 'password': encoded, 'password_hash': encoded})
        for membership_id, household_id, user_id, email, role in (
            ('membership-existing-own', 'hh-own', 'existing-user', 'existing@example.com', 'admin'),
            ('membership-wrong-own', 'hh-own', 'wrong-user', 'wrong@example.com', 'member'),
            ('membership-invite-admin', 'hh-invite', 'invite-admin', 'invite-admin@example.com', 'admin'),
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


def _application(engine) -> FastAPI:
    config = SessionApiConfiguration(cookie_secure=False, cookie_samesite='lax')
    app = FastAPI()
    app.include_router(create_household_invitation_acceptance_router(engine, config))
    app.include_router(create_session_household_router(engine, config))
    return app


def _create_invitation(engine, email: str) -> str:
    with engine.begin() as conn:
        result = create_household_invitation(
            conn,
            household_id='hh-invite',
            invitee_email=email,
            created_by_user_id='invite-admin',
        )
        return result.raw_token


def _session(engine, user_id: str, household_id: str) -> str:
    with engine.begin() as conn:
        raw, _ = create_server_session(
            conn,
            user_id=user_id,
            active_household_id=household_id,
        )
        return raw


def _set_test_session_cookie(client: TestClient, raw_session: str) -> None:
    client.cookies.set(
        SESSION_COOKIE_NAME,
        raw_session,
        domain='testserver.local',
        path='/',
    )


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix='rezzerv-invitation-acceptance-') as tmp:
        database_path = Path(tmp) / 'acceptance.db'
        engine = migrated_sqlite_engine(database_path, check_same_thread=False)
        _prepare_database(engine)
        app = _application(engine)

        existing_token = _create_invitation(engine, 'existing@example.com')
        with TestClient(app) as anonymous:
            preview = anonymous.get(f'/api/household/invitations/accept/{existing_token}')
            assert preview.status_code == 200, preview.text
            body = preview.json()
            assert body['household_name'] == 'Samen thuis'
            assert body['account_exists'] is True
            assert body['invitee_email_masked'] != 'existing@example.com'
            assert 'token_hash' not in body
            assert 'household_id' not in body
        checks.append('public_preview_is_token_bound_and_minimally_disclosing')

        wrong_session = _session(engine, 'wrong-user', 'hh-own')
        with TestClient(app) as wrong_client:
            _set_test_session_cookie(wrong_client, wrong_session)
            wrong_accept = wrong_client.post(
                f'/api/household/invitations/accept/{existing_token}', json={}
            )
            assert wrong_accept.status_code == 403, wrong_accept.text
        with engine.begin() as conn:
            status_value = conn.execute(text(
                "SELECT status FROM household_invitations WHERE invitee_email = 'existing@example.com'"
            )).scalar_one()
            assert status_value == 'pending'
            count = int(conn.execute(text("""
                SELECT COUNT(*) FROM household_memberships
                WHERE household_id = 'hh-invite' AND user_email = 'existing@example.com'
            """)).scalar_one())
            assert count == 0
        checks.append('wrong_logged_in_email_cannot_consume_invitation')

        existing_session = _session(engine, 'existing-user', 'hh-own')
        with TestClient(app) as existing_client:
            _set_test_session_cookie(existing_client, existing_session)
            accepted = existing_client.post(
                f'/api/household/invitations/accept/{existing_token}', json={}
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()['active_household_id'] == 'hh-invite'
            assert accepted.json()['role'] == 'member'
            current_cookie = existing_client.cookies.get(
                SESSION_COOKIE_NAME,
                domain='testserver.local',
                path='/',
            )
            assert current_cookie and current_cookie != existing_session

            households = existing_client.get('/api/session/households')
            assert households.status_code == 200, households.text
            items = households.json()['items']
            assert {item['household_id'] for item in items} == {'hh-own', 'hh-invite'}
            assert households.json()['can_switch_households'] is True

            switch_back = existing_client.post('/api/session/household', json={'household_id': 'hh-own'})
            assert switch_back.status_code == 200, switch_back.text
            assert switch_back.json()['active_household_id'] == 'hh-own'
            forged = existing_client.post('/api/session/household', json={'household_id': 'hh-other'})
            assert forged.status_code == 403, forged.text
        with engine.begin() as conn:
            membership = conn.execute(text("""
                SELECT id, role FROM household_memberships
                WHERE household_id = 'hh-invite' AND user_email = 'existing@example.com'
            """)).mappings().one()
            canonical = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id = 'hh-invite' AND membership_id = :membership_id AND active = 1
            """), {'membership_id': membership['id']}).scalar_one()
            assert membership['role'] == 'member'
            assert canonical == 'household.member'
            accepted_status = conn.execute(text("""
                SELECT status, accepted_by_user_id, accepted_at
                FROM household_invitations WHERE invitee_email = 'existing@example.com'
            """)).mappings().one()
            assert accepted_status['status'] == 'accepted'
            assert accepted_status['accepted_by_user_id'] == 'existing-user'
            assert accepted_status['accepted_at']
        checks.append('existing_account_accepts_atomically_and_can_switch_households')

        with TestClient(app) as replay_client:
            _set_test_session_cookie(
                replay_client,
                _session(engine, 'existing-user', 'hh-own'),
            )
            replay = replay_client.post(
                f'/api/household/invitations/accept/{existing_token}', json={}
            )
            assert replay.status_code == 409, replay.text
        checks.append('accepted_token_is_single_use')

        new_token = _create_invitation(engine, 'new-person@example.com')
        with engine.begin() as conn:
            households_before = int(conn.execute(text('SELECT COUNT(*) FROM household_registry')).scalar_one())
        with TestClient(app) as new_client:
            registered = new_client.post(
                f'/api/household/invitations/accept/{new_token}/register',
                json={'email': 'new-person@example.com', 'password': 'NewPersonPassword123'},
            )
            assert registered.status_code == 201, registered.text
            assert registered.json()['active_household_id'] == 'hh-invite'
            assert registered.json()['role'] == 'member'
            assert new_client.cookies.get(
                SESSION_COOKIE_NAME,
                domain='testserver.local',
                path='/',
            )
        with engine.begin() as conn:
            households_after = int(conn.execute(text('SELECT COUNT(*) FROM household_registry')).scalar_one())
            assert households_after == households_before
            user = conn.execute(text(
                "SELECT id FROM app_users WHERE email = 'new-person@example.com'"
            )).mappings().one()
            memberships = conn.execute(text("""
                SELECT household_id, role FROM household_memberships
                WHERE user_email = 'new-person@example.com'
            """)).mappings().all()
            assert len(memberships) == 1
            assert memberships[0]['household_id'] == 'hh-invite'
            assert memberships[0]['role'] == 'member'
        checks.append('invited_registration_creates_no_extra_household')

        mismatch_token = _create_invitation(engine, 'bound-person@example.com')
        with TestClient(app) as mismatch_client:
            mismatch = mismatch_client.post(
                f'/api/household/invitations/accept/{mismatch_token}/register',
                json={'email': 'other-person@example.com', 'password': 'OtherPersonPassword123'},
            )
            assert mismatch.status_code == 403, mismatch.text
        with engine.begin() as conn:
            leaked_account = int(conn.execute(text(
                "SELECT COUNT(*) FROM app_users WHERE email = 'other-person@example.com'"
            )).scalar_one())
            assert leaked_account == 0
            pending = conn.execute(text(
                "SELECT status FROM household_invitations WHERE invitee_email = 'bound-person@example.com'"
            )).scalar_one()
            assert pending == 'pending'
        checks.append('wrong_registration_email_rolls_back_account_and_preserves_invitation')

        existing_account_token = _create_invitation(engine, 'wrong@example.com')
        with TestClient(app) as account_exists_client:
            conflict = account_exists_client.post(
                f'/api/household/invitations/accept/{existing_account_token}/register',
                json={'email': 'wrong@example.com', 'password': 'CannotReplaceAccount123'},
            )
            assert conflict.status_code == 409, conflict.text
        checks.append('registration_path_never_replaces_existing_account')

        with engine.begin() as conn:
            audits = conn.execute(text("""
                SELECT action, object_type, new_value FROM auth_audit_log
                WHERE action = 'household.invitation.accepted'
                ORDER BY created_at, object_id
            """)).mappings().all()
            assert len(audits) >= 2
            assert all(row['object_type'] == 'household_invitation' for row in audits)
            assert all('household.member' in str(row['new_value']) for row in audits)
            assert all('token' not in str(row['new_value']).lower() for row in audits)
        checks.append('acceptance_is_audited_without_token_material')

    for check in checks:
        print(f'PASS {check}')
    print(f'RESULT {len(checks)}/{len(checks)} checks passed')
    print('HOUSEHOLD_INVITATION_ACCEPTANCE_GREEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
