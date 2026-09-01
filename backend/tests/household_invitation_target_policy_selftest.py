"""Self-contained validation for I.1 invitation target account policy."""

from __future__ import annotations

from sqlalchemy import text

from app.services.household_invitation_target_policy import (
    InvitationTargetNotAllowedError,
    assert_household_invitation_target_allowed,
)
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from household_invitation_migrated_fixture import insert_user, migrated_postgresql_engine


def _expect_blocked(conn, email: str) -> None:
    try:
        assert_household_invitation_target_allowed(conn, email)
    except InvitationTargetNotAllowedError:
        return
    raise AssertionError(f'platform identity unexpectedly allowed: {email}')


def run() -> int:
    checks: list[str] = []
    engine = migrated_postgresql_engine()
    try:
        with engine.begin() as conn:
            for user_id, email in (
                ('ordinary', 'ordinary@example.com'),
                ('super', 'platform-super@example.com'),
                ('front', 'frontteam@example.com'),
                ('platform-admin', 'platform-admin@example.com'),
                ('ip-owner', 'ip-owner@example.com'),
                ('inactive', 'inactive-platform@example.com'),
            ):
                insert_user(conn, user_id=user_id, email=email)
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active) VALUES
                    ('super', 'platform.superuser', TRUE),
                    ('front', 'platform.frontteam', TRUE),
                    ('platform-admin', 'platform.platform_admin', TRUE),
                    ('ip-owner', 'platform.ip_owner', TRUE),
                    ('inactive', 'platform.frontteam', FALSE)
            """))

        with engine.begin() as conn:
            assert_household_invitation_target_allowed(conn, 'new-user@example.com')
            assert_household_invitation_target_allowed(conn, 'ordinary@example.com')
            assert_household_invitation_target_allowed(conn, 'inactive-platform@example.com')
        checks.append('ordinary_new_and_inactive_platform_accounts_are_allowed')

        with engine.begin() as conn:
            _expect_blocked(conn, SUPERGEBRUIKER_EMAIL)
        checks.append('reserved_superuser_email_is_blocked')

        with engine.begin() as conn:
            for email in (
                'platform-super@example.com',
                'frontteam@example.com',
                'platform-admin@example.com',
                'ip-owner@example.com',
            ):
                _expect_blocked(conn, email)
        checks.append('all_active_platform_managed_identities_are_blocked')
    finally:
        engine.dispose()

    for check in checks:
        print(f'PASS {check}')
    print(f'RESULT {len(checks)}/{len(checks)} checks passed')
    print('HOUSEHOLD_INVITATION_TARGET_POLICY_GREEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
