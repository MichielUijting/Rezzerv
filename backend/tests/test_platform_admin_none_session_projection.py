from datetime import datetime, timedelta, timezone

from app.services.authorization_foundation_service import (
    HOUSEHOLD_PERMISSIONS,
    ROLE_PERMISSIONS,
)
from app.services.server_session_service import (
    ServerSessionContext,
    public_session_payload,
)


def test_platform_admin_none_session_projects_exact_platform_permissions():
    issued_at = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    context = ServerSessionContext(
        session_id="session-platform-admin",
        user_id="platform-admin",
        email="platform@example.test",
        active_household_id=None,
        context_type="none",
        role=None,
        session_version=1,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=12),
    )
    payload = public_session_payload(context)
    expected_permissions = set(ROLE_PERMISSIONS["platform.platform_admin"])
    granted_permissions = {
        key for key, allowed in payload["permissions"].items() if allowed
    }

    assert granted_permissions == expected_permissions
    assert payload["supported_permissions"] == sorted(expected_permissions)
    assert not granted_permissions.intersection(HOUSEHOLD_PERMISSIONS)
    assert payload["active_household_id"] is None
    assert payload["active_household_name"] == ""
    assert payload["context_type"] == "none"
    assert payload["role"] is None
    assert payload["display_role"] is None
    assert payload["can_manage_member_permissions"] is False
    assert payload["can_manage_members"] is False
    assert payload["is_viewer"] is False
    assert payload["is_platform_superuser"] is False
    assert payload["is_frontteam"] is False
    assert "platform_roles" not in payload
