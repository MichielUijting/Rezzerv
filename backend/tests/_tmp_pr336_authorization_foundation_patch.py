from pathlib import Path

path = Path('backend/app/services/authorization_foundation_service.py')
source = path.read_text(encoding='utf-8')

old_import = 'from sqlalchemy import text\n'
new_import = 'from sqlalchemy import inspect, text\n'
if source.count(old_import) != 1:
    raise SystemExit(f'Expected one sqlalchemy text import, found {source.count(old_import)}')
source = source.replace(old_import, new_import, 1)

start_marker = 'def ensure_authorization_foundation(conn) -> None:\n'
end_marker = '\ndef _seed_registry(conn) -> None:\n'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('Authorization foundation function boundaries not found')

replacement = '''_AUTHORIZATION_FOUNDATION_COLUMNS = {
    "auth_permissions": {"permission_key", "scope", "description", "active", "created_at"},
    "auth_roles": {"role_key", "scope", "name", "system_role", "active", "created_at"},
    "auth_role_permissions": {"role_key", "permission_key", "created_at"},
    "auth_membership_roles": {
        "household_id", "membership_id", "role_key", "active", "created_at", "updated_at",
    },
    "auth_membership_permission_overrides": {
        "household_id", "membership_id", "permission_key", "effect", "reason", "created_at", "updated_at",
    },
    "auth_platform_user_roles": {"user_id", "role_key", "active", "created_at", "updated_at"},
    "auth_support_sessions": {
        "id", "support_user_id", "household_id", "access_level", "reason", "ticket_reference",
        "starts_at", "expires_at", "revoked_at", "created_at",
    },
    "auth_audit_log": {
        "id", "actor_user_id", "actor_type", "household_id", "support_session_id", "action",
        "object_type", "object_id", "old_value", "new_value", "reason", "ticket_reference", "created_at",
    },
}
_AUTHORIZATION_IP_OWNER_INDEX = "idx_auth_single_active_ip_owner"


def validate_authorization_foundation_schema(conn) -> None:
    """Fail closed when Alembic has not installed the authorization contract."""
    inspector = inspect(conn)
    available_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(_AUTHORIZATION_FOUNDATION_COLUMNS) - available_tables)
    if missing_tables:
        raise RuntimeError(
            "Authorization foundation is niet gemigreerd; ontbrekende tabellen: "
            + ", ".join(missing_tables)
        )

    for table_name, required_columns in _AUTHORIZATION_FOUNDATION_COLUMNS.items():
        actual_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"Authorization foundation schema drift voor {table_name}; "
                f"ontbrekende kolommen: {', '.join(missing_columns)}"
            )

    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes("auth_platform_user_roles")
    }
    ip_owner_index = indexes.get(_AUTHORIZATION_IP_OWNER_INDEX)
    if not ip_owner_index:
        raise RuntimeError(
            f"Authorization foundation index ontbreekt: {_AUTHORIZATION_IP_OWNER_INDEX}"
        )
    if not bool(ip_owner_index.get("unique")) or tuple(ip_owner_index.get("column_names") or ()) != ("role_key",):
        raise RuntimeError(
            "Authorization foundation IP-owner index wijkt af in uniqueness/kolommen"
        )


def ensure_authorization_foundation(conn) -> None:
    """Validate Alembic-owned schema and seed canonical registry rows using DML only."""
    validate_authorization_foundation_schema(conn)
    _seed_registry(conn)

'''
source = source[:start] + replacement + source[end + 1:]

path.write_text(source, encoding='utf-8')
print('AUTHORIZATION_FOUNDATION_RUNTIME_DDL_REMOVED')
