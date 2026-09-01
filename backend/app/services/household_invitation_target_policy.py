from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


class InvitationTargetNotAllowedError(ValueError):
    pass


def assert_household_invitation_target_allowed(conn: Connection, invitee_email: str) -> None:
    """Reject platform-managed identities from the regular household invite flow."""

    normalized_email = str(invitee_email or "").strip().lower()
    if not normalized_email:
        raise ValueError("E-mailadres ontbreekt")
    if normalized_email == SUPERGEBRUIKER_EMAIL:
        raise InvitationTargetNotAllowedError(
            "Dit platformaccount kan niet via een huishoudelijke uitnodiging worden gekoppeld"
        )

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "app_users" not in tables or "auth_platform_user_roles" not in tables:
        return
    user_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("app_users")
    }
    if "id" not in user_columns or "email" not in user_columns:
        return

    platform_identity = conn.execute(
        text(
            """
            SELECT 1
            FROM app_users u
            JOIN auth_platform_user_roles pur ON pur.user_id = u.id
            WHERE lower(trim(u.email)) = :email
              AND pur.active = TRUE
            LIMIT 1
            """
        ),
        {"email": normalized_email},
    ).first()
    if platform_identity:
        raise InvitationTargetNotAllowedError(
            "Dit platformaccount kan niet via een huishoudelijke uitnodiging worden gekoppeld"
        )
