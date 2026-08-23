from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_onboarding_service import start_new_household_onboarding
from app.services.password_service import hash_password
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL

DEFAULT_CONSUMER_HOUSEHOLD_NAME = "Mijn huishouden"


class ConsumerAccountExistsError(ValueError):
    pass


@dataclass(frozen=True)
class ConsumerAccountProvisioningResult:
    user_id: str
    email: str
    household_id: str
    membership_id: str


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def provision_new_consumer_account(
    conn,
    *,
    email: str,
    password: str,
    household_name: str = DEFAULT_CONSUMER_HOUSEHOLD_NAME,
) -> ConsumerAccountProvisioningResult:
    """Create one regular consumer, household and canonical admin membership atomically."""

    normalized_email = str(email or "").strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("Geldig e-mailadres is verplicht")
    if normalized_email == SUPERGEBRUIKER_EMAIL:
        raise ConsumerAccountExistsError("Account is niet beschikbaar")

    ensure_authorization_foundation(conn)

    user_columns = _columns(conn, "app_users")
    household_columns = _columns(conn, "household_registry")
    membership_columns = _columns(conn, "household_memberships")

    user_id_column = _pick(user_columns, "id", "user_id")
    user_email_column = _pick(user_columns, "email", "user_email")
    user_password_column = _pick(user_columns, "password")
    household_id_column = _pick(household_columns, "id", "household_id")
    household_name_column = _pick(household_columns, "naam", "name")
    membership_id_column = _pick(membership_columns, "id", "membership_id")
    membership_household_column = _pick(membership_columns, "household_id")
    membership_email_column = _pick(membership_columns, "user_email", "email")
    membership_user_column = _pick(membership_columns, "user_id")
    membership_role_column = _pick(membership_columns, "role", "rol")

    if not user_id_column or not user_email_column or not user_password_column:
        raise RuntimeError("app_users mist de vereiste accountkolommen")
    if not household_id_column or not household_name_column:
        raise RuntimeError("household_registry mist de vereiste huishoudkolommen")
    if (
        not membership_id_column
        or not membership_household_column
        or not membership_role_column
        or (not membership_email_column and not membership_user_column)
    ):
        raise RuntimeError("household_memberships mist de vereiste lidmaatschapskolommen")

    existing = conn.execute(
        text(
            f"SELECT {user_id_column} FROM app_users "
            f"WHERE lower(trim({user_email_column})) = :email LIMIT 1"
        ),
        {"email": normalized_email},
    ).first()
    if existing:
        raise ConsumerAccountExistsError("Account bestaat al")

    user_id = str(uuid.uuid4())
    household_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())
    encoded_password = hash_password(password)

    user_insert_columns = [user_id_column, user_email_column, user_password_column]
    user_insert_values = [":user_id", ":email", ":password"]
    user_params = {
        "user_id": user_id,
        "email": normalized_email,
        "password": encoded_password,
    }
    if "password_hash" in user_columns:
        user_insert_columns.append("password_hash")
        user_insert_values.append(":password_hash")
        user_params["password_hash"] = encoded_password
    if "account_status" in user_columns:
        user_insert_columns.append("account_status")
        user_insert_values.append("'active'")
    if "created_at" in user_columns:
        user_insert_columns.append("created_at")
        user_insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in user_columns:
        user_insert_columns.append("updated_at")
        user_insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO app_users ({', '.join(user_insert_columns)}) "
            f"VALUES ({', '.join(user_insert_values)})"
        ),
        user_params,
    )

    household_insert_columns = [household_id_column, household_name_column]
    household_insert_values = [":household_id", ":household_name"]
    household_params = {
        "household_id": household_id,
        "household_name": str(household_name or DEFAULT_CONSUMER_HOUSEHOLD_NAME).strip()
        or DEFAULT_CONSUMER_HOUSEHOLD_NAME,
    }
    if "context_type" in household_columns:
        household_insert_columns.append("context_type")
        household_insert_values.append("'regular'")
    if "created_at" in household_columns:
        household_insert_columns.append("created_at")
        household_insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in household_columns:
        household_insert_columns.append("updated_at")
        household_insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO household_registry ({', '.join(household_insert_columns)}) "
            f"VALUES ({', '.join(household_insert_values)})"
        ),
        household_params,
    )

    membership_insert_columns = [
        membership_id_column,
        membership_household_column,
        membership_role_column,
    ]
    membership_insert_values = [":membership_id", ":household_id", "'admin'"]
    membership_params = {
        "membership_id": membership_id,
        "household_id": household_id,
        "email": normalized_email,
        "user_id": user_id,
    }
    if membership_email_column:
        membership_insert_columns.append(membership_email_column)
        membership_insert_values.append(":email")
    if membership_user_column:
        membership_insert_columns.append(membership_user_column)
        membership_insert_values.append(":user_id")
    if "status" in membership_columns:
        membership_insert_columns.append("status")
        membership_insert_values.append("'active'")
    if "active" in membership_columns:
        membership_insert_columns.append("active")
        membership_insert_values.append("1")
    if "created_at" in membership_columns:
        membership_insert_columns.append("created_at")
        membership_insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in membership_columns:
        membership_insert_columns.append("updated_at")
        membership_insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO household_memberships ({', '.join(membership_insert_columns)}) "
            f"VALUES ({', '.join(membership_insert_values)})"
        ),
        membership_params,
    )

    role_key = create_canonical_membership_role(
        conn,
        household_id=household_id,
        membership_id=membership_id,
        legacy_role="admin",
    )
    if role_key != "household.admin":
        raise RuntimeError("Nieuwe consument kreeg geen canonieke Beheerder-rol")

    onboarding = start_new_household_onboarding(conn, household_id)
    if not onboarding.initial_choice_required:
        raise RuntimeError("Nieuw huishouden kreeg geen initiële onboardingstatus")

    return ConsumerAccountProvisioningResult(
        user_id=user_id,
        email=normalized_email,
        household_id=household_id,
        membership_id=membership_id,
    )
