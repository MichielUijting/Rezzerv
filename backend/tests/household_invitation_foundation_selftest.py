"""Self-contained validation for Onboarding v2 I.1 household invitations."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.household_invitation_routes import create_household_invitation_router
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_invitation_service import (
    InvitationConflictError,
    create_household_invitation,
    hash_invitation_token,
    resolve_pending_invitation_token,
    revoke_household_invitation,
    utc_now,
)
from app.services.server_session_service import (
    SESSION_COOKIE_NAME,
    create_server_session,
    create_system_server_session,
)


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                account_status TEXT NOT NULL DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(household_id, user_email)
            )
        """))
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type) VALUES
                ('hh-a', 'Huis A', 'regular'),
                ('hh-b', 'Huis B', 'regular'),
                ('0', 'Systeem', 'system')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, account_status) VALUES
                ('admin-a', 'admin-a@example.com', 'active'),
                ('member-a', 'member-a@example.com', 'active'),
                ('existing-a', 'existing-a@example.com', 'active'),
                ('admin-b', 'admin-b@example.com', 'active'),
                ('system-user', 'system@example.com', 'active')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(
                id, household_id, user_id, user_email, role, status
            ) VALUES
                ('membership-admin-a', 'hh-a', 'admin-a', 'admin-a@example.com', 'admin', 'active'),
                ('membership-member-a', 'hh-a', 'member-a', 'member-a@example.com', 'member', 'active'),
                ('membership-existing-a', 'hh-a', 'existing-a', 'existing-a@example.com', 'member', 'active'),
                ('membership-admin-b', 'hh-b', 'admin-b', 'admin-b@example.com', 'admin', 'active')
        """))
        create_canonical_membership_role(
            conn,
            household_id='hh-a',
            membership_id='membership-admin-a',
            legacy_role='admin',
        )
        create_canonical_membership_role(
            conn,
            household_id='hh-a',
            membership_id='membership-member-a',
            legacy_role='member',
        )
        create_canonical_membership_role(
            conn,
            household_id='hh-a',
            membership_id='membership-existing-a',
            legacy_role='member',
        )
        create_canonical_membership_role(
            conn,
            household_id='hh-b',
            membership_id='membership-admin-b',
            legacy_role='admin',
        )
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('system-user', 'platform.superuser', 1)
        """))


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(create_household_invitation_router(engine))
    return app


def _regular_session(engine, *, user_id: str, household_id: str) -> str:
    with engine.begin() as conn:
        raw, _ = create_server_session(
            conn,
            user_id=user_id,
            active_household_id=household_id,
        )
    return raw


def _system_session(engine) -> str:
    with engine.begin() as conn:
        raw, _ = create_system_server_session(conn, user_id='system-user')
    return raw


def _client_with_cookie(app: FastAPI, raw_session: str) -> TestClient:
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, raw_session)
    return client


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix='rezzerv-invitation-foundation-') as tmp:
        database_path = Path(tmp) / 'invitation.db'
        engine = create_engine(
            f'sqlite:///{database_path}',
            future=True,
            connect_args={'check_same_thread': False},
        )
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            response = anonymous.post(
                '/api/household/invitations',
                json={'email': 'anonymous@example.com'},
            )
            assert response.status_code == 401, response.text
        checks.append('anonymous_cannot_create_invitation')

        member_raw = _regular_session(engine, user_id='member-a', household_id='hh-a')
        with _client_with_cookie(app, member_raw) as member:
            forbidden = member.post(
                '/api/household/invitations',
                json={'email': 'member-target@example.com'},
            )
            assert forbidden.status_code == 403, forbidden.text
            detail = forbidden.json()['detail']
            assert detail['permission_key'] == 'members.manage'
        checks.append('member_without_members_manage_is_denied')

        system_raw = _system_session(engine)
        with _client_with_cookie(app, system_raw) as system_client:
            forbidden = system_client.post(
                '/api/household/invitations',
                json={'email': 'system-target@example.com'},
            )
            assert forbidden.status_code == 403, forbidden.text
        checks.append('system_context_cannot_manage_household_invitations')

        admin_raw = _regular_session(engine, user_id='admin-a', household_id='hh-a')
        with _client_with_cookie(app, admin_raw) as admin:
            forged = admin.post(
                '/api/household/invitations',
                json={
                    'email': 'forged@example.com',
                    'household_id': 'hh-b',
                    'role': 'household.admin',
                    'password': 'NeverAcceptThis',
                },
            )
            assert forged.status_code == 422, forged.text
        checks.append('browser_cannot_supply_household_role_or_password')

        with engine.begin() as conn:
            users_before = int(conn.execute(text('SELECT COUNT(*) FROM app_users')).scalar_one())
            memberships_before = int(conn.execute(text('SELECT COUNT(*) FROM household_memberships')).scalar_one())

        with _client_with_cookie(app, admin_raw) as admin:
            created = admin.post(
                '/api/household/invitations',
                json={'email': '  Candidate@Example.com  '},
            )
            assert created.status_code == 201, created.text
            payload = created.json()
            invitation = payload['invitation']
            assert payload['ok'] is True
            assert invitation['household_id'] == 'hh-a'
            assert invitation['invitee_email'] == 'candidate@example.com'
            assert invitation['role_key'] == 'household.member'
            assert invitation['status'] == 'pending'
            assert 'token' not in payload
            assert 'raw_token' not in payload
            assert 'token_hash' not in invitation
            invitation_id = invitation['id']

        with engine.begin() as conn:
            users_after = int(conn.execute(text('SELECT COUNT(*) FROM app_users')).scalar_one())
            memberships_after = int(conn.execute(text('SELECT COUNT(*) FROM household_memberships')).scalar_one())
            assert users_after == users_before
            assert memberships_after == memberships_before
            stored = conn.execute(text("""
                SELECT token_hash, status, role_key, expires_at, created_at
                FROM household_invitations
                WHERE id = :id
            """), {'id': invitation_id}).mappings().one()
            assert len(str(stored['token_hash'])) == 64
            assert stored['status'] == 'pending'
            assert stored['role_key'] == 'household.member'
            audit = conn.execute(text("""
                SELECT new_value
                FROM auth_audit_log
                WHERE action = 'household.invitation.created'
                  AND object_id = :id
            """), {'id': invitation_id}).mappings().one()
            serialized_audit = str(audit['new_value'])
            assert 'token' not in serialized_audit
            assert 'hash' not in serialized_audit
        checks.append('create_is_pending_hash_only_and_creates_no_account_or_membership')

        with _client_with_cookie(app, admin_raw) as admin:
            duplicate = admin.post(
                '/api/household/invitations',
                json={'email': 'candidate@example.com'},
            )
            assert duplicate.status_code == 409, duplicate.text
            existing_member = admin.post(
                '/api/household/invitations',
                json={'email': 'existing-a@example.com'},
            )
            assert existing_member.status_code == 409, existing_member.text
        checks.append('duplicate_pending_and_existing_member_are_rejected')

        with _client_with_cookie(app, admin_raw) as admin:
            listed = admin.get('/api/household/invitations')
            assert listed.status_code == 200, listed.text
            body = listed.json()
            assert body['household_id'] == 'hh-a'
            assert body['total'] >= 1
            listed_invitation = next(item for item in body['items'] if item['id'] == invitation_id)
            assert 'token_hash' not in listed_invitation
            assert listed_invitation['status'] == 'pending'
        checks.append('list_is_household_scoped_and_never_exposes_token_hash')

        with _client_with_cookie(app, admin_raw) as admin:
            revoked = admin.post(f'/api/household/invitations/{invitation_id}/revoke')
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()['invitation']['status'] == 'revoked'
            second_revoke = admin.post(f'/api/household/invitations/{invitation_id}/revoke')
            assert second_revoke.status_code == 409, second_revoke.text
        with engine.begin() as conn:
            audit = conn.execute(text("""
                SELECT old_value, new_value
                FROM auth_audit_log
                WHERE action = 'household.invitation.revoked'
                  AND object_id = :id
            """), {'id': invitation_id}).mappings().one()
            assert 'pending' in str(audit['old_value'])
            assert 'revoked' in str(audit['new_value'])
        checks.append('revoke_is_single_transition_and_is_audited')

        admin_b_raw = _regular_session(engine, user_id='admin-b', household_id='hh-b')
        with _client_with_cookie(app, admin_b_raw) as admin_b:
            created_b = admin_b.post(
                '/api/household/invitations',
                json={'email': 'cross-household@example.com'},
            )
            assert created_b.status_code == 201, created_b.text
            invitation_b_id = created_b.json()['invitation']['id']
        with _client_with_cookie(app, admin_raw) as admin_a:
            cross_revoke = admin_a.post(
                f'/api/household/invitations/{invitation_b_id}/revoke'
            )
            assert cross_revoke.status_code == 404, cross_revoke.text
            household_a_list = admin_a.get('/api/household/invitations').json()['items']
            assert all(item['id'] != invitation_b_id for item in household_a_list)
        checks.append('cross_household_invitation_ids_do_not_escape_session_household')

        old_now = utc_now() - timedelta(days=8)
        with engine.begin() as conn:
            old = create_household_invitation(
                conn,
                household_id='hh-a',
                invitee_email='expired@example.com',
                created_by_user_id='admin-a',
                now=old_now,
            )
            old_invitation_id = str(old.invitation['id'])
        with _client_with_cookie(app, admin_raw) as admin:
            replacement = admin.post(
                '/api/household/invitations',
                json={'email': 'expired@example.com'},
            )
            assert replacement.status_code == 201, replacement.text
            replacement_id = replacement.json()['invitation']['id']
            assert replacement_id != old_invitation_id
        with engine.begin() as conn:
            old_status = conn.execute(text(
                'SELECT status FROM household_invitations WHERE id = :id'
            ), {'id': old_invitation_id}).scalar_one()
            assert old_status == 'expired'
        checks.append('expired_pending_invitation_is_closed_before_reinvite')

        with engine.begin() as conn:
            token_result = create_household_invitation(
                conn,
                household_id='hh-b',
                invitee_email='token-check@example.com',
                created_by_user_id='admin-b',
            )
            token_id = str(token_result.invitation['id'])
            raw_token = token_result.raw_token
            stored_hash = conn.execute(text(
                'SELECT token_hash FROM household_invitations WHERE id = :id'
            ), {'id': token_id}).scalar_one()
            assert raw_token != stored_hash
            assert hash_invitation_token(raw_token) == stored_hash
            resolved = resolve_pending_invitation_token(conn, raw_token=raw_token)
            assert resolved['id'] == token_id
            revoke_household_invitation(
                conn,
                household_id='hh-b',
                invitation_id=token_id,
                actor_user_id='admin-b',
            )
            try:
                resolve_pending_invitation_token(conn, raw_token=raw_token)
            except InvitationConflictError:
                pass
            else:
                raise AssertionError('revoked token unexpectedly remained valid')
        checks.append('raw_token_is_hash_only_at_rest_and_revocation_invalidates_resolution')

    for check in checks:
        print(f'PASS {check}')
    print(f'RESULT {len(checks)}/{len(checks)} checks passed')
    print('HOUSEHOLD_INVITATION_FOUNDATION_GREEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
