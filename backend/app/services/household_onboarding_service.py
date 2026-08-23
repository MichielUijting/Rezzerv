from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text

ONBOARDING_VERSION = 2
ONBOARDING_STATUS_NOT_STARTED = "not_started"
ONBOARDING_STATUS_IN_PROGRESS = "in_progress"
ONBOARDING_STATUS_COMPLETED = "completed"
ONBOARDING_STATUSES = frozenset({
    ONBOARDING_STATUS_NOT_STARTED,
    ONBOARDING_STATUS_IN_PROGRESS,
    ONBOARDING_STATUS_COMPLETED,
})
PRIMARY_USE_CASES = frozenset({
    "inhuis_halen",
    "wat_inhuis",
    "waar_inhuis",
})
HOUSEHOLD_USAGE_MODES = frozenset({"alone", "together"})
PROFILE_FOLLOW_UP_STEP = "profile_follow_up"
SHARED_HOUSEHOLD_MINIMUM_STEP = "shared_household_minimum"


class OnboardingAlreadyCompletedError(ValueError):
    pass


@dataclass(frozen=True)
class HouseholdOnboardingState:
    household_id: str
    household_name: str
    onboarding_status: str
    onboarding_version: int
    primary_use_case: str | None
    onboarding_step: str | None
    household_usage_mode: str | None
    onboarding_completed_at: str | None

    @property
    def initial_choice_required(self) -> bool:
        return (
            self.onboarding_status == ONBOARDING_STATUS_NOT_STARTED
            and not self.primary_use_case
        )

    @property
    def profile_follow_up_required(self) -> bool:
        return (
            self.onboarding_status == ONBOARDING_STATUS_IN_PROGRESS
            and self.primary_use_case in PRIMARY_USE_CASES
            and self.onboarding_step == PROFILE_FOLLOW_UP_STEP
        )

    @property
    def shared_household_minimum_required(self) -> bool:
        return (
            self.onboarding_status == ONBOARDING_STATUS_IN_PROGRESS
            and self.primary_use_case in PRIMARY_USE_CASES
            and self.onboarding_step == SHARED_HOUSEHOLD_MINIMUM_STEP
        )


def _household_registry_columns(conn) -> set[str]:
    inspector = inspect(conn)
    if "household_registry" not in inspector.get_table_names():
        return set()
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns("household_registry")
    }


def _household_onboarding_columns(conn) -> set[str]:
    inspector = inspect(conn)
    if "household_onboarding" not in inspector.get_table_names():
        return set()
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns("household_onboarding")
    }


def _household_registry_identity_columns(conn) -> tuple[str, str]:
    columns = _household_registry_columns(conn)
    household_id_column = "id" if "id" in columns else (
        "household_id" if "household_id" in columns else None
    )
    household_name_column = "naam" if "naam" in columns else (
        "name" if "name" in columns else None
    )
    if not household_id_column or not household_name_column:
        raise RuntimeError("household_registry mist bruikbare id-/naamkolommen")
    return household_id_column, household_name_column


def _normalize_household_name(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise ValueError("Naam huishouden is verplicht")
    if len(normalized) > 120:
        raise ValueError("Naam huishouden mag maximaal 120 tekens bevatten")
    return normalized


def ensure_household_onboarding_foundation(conn) -> None:
    """Create onboarding state and mark pre-existing regular households complete.

    The migration is deliberately forward-only: households that already existed
    before onboarding v2 are never forced through the new flow. A newly created
    consumer household is explicitly reset to ``not_started`` by
    ``start_new_household_onboarding`` in the same registration transaction.

    The shared household minimum was added after the first profile slices. It is
    therefore added as a nullable column and existing completed households are
    deliberately not reopened.
    """

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS household_onboarding (
            household_id TEXT PRIMARY KEY,
            onboarding_status TEXT NOT NULL
                CHECK (onboarding_status IN ('not_started', 'in_progress', 'completed')),
            onboarding_version INTEGER NOT NULL DEFAULT 2,
            primary_use_case TEXT
                CHECK (
                    primary_use_case IS NULL
                    OR primary_use_case IN ('inhuis_halen', 'wat_inhuis', 'waar_inhuis')
                ),
            onboarding_step TEXT,
            household_usage_mode TEXT
                CHECK (
                    household_usage_mode IS NULL
                    OR household_usage_mode IN ('alone', 'together')
                ),
            onboarding_completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    onboarding_columns = _household_onboarding_columns(conn)
    if "household_usage_mode" not in onboarding_columns:
        conn.execute(text(
            "ALTER TABLE household_onboarding ADD COLUMN household_usage_mode TEXT"
        ))

    columns = _household_registry_columns(conn)
    household_id_column = "id" if "id" in columns else (
        "household_id" if "household_id" in columns else None
    )
    if not household_id_column:
        raise RuntimeError("household_registry heeft geen bruikbare identificatiekolom")

    if "context_type" in columns:
        regular_predicate = "lower(trim(COALESCE(context_type, 'regular'))) = 'regular'"
    else:
        regular_predicate = f"CAST({household_id_column} AS TEXT) <> '0'"

    conn.execute(text(f"""
        INSERT OR IGNORE INTO household_onboarding (
            household_id,
            onboarding_status,
            onboarding_version,
            primary_use_case,
            onboarding_step,
            household_usage_mode,
            onboarding_completed_at,
            created_at,
            updated_at
        )
        SELECT
            CAST({household_id_column} AS TEXT),
            'completed',
            :onboarding_version,
            NULL,
            NULL,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM household_registry
        WHERE {regular_predicate}
    """), {"onboarding_version": ONBOARDING_VERSION})


def start_new_household_onboarding(conn, household_id: str) -> HouseholdOnboardingState:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    ensure_household_onboarding_foundation(conn)
    conn.execute(text("""
        INSERT INTO household_onboarding (
            household_id,
            onboarding_status,
            onboarding_version,
            primary_use_case,
            onboarding_step,
            household_usage_mode,
            onboarding_completed_at,
            created_at,
            updated_at
        ) VALUES (
            :household_id,
            'not_started',
            :onboarding_version,
            NULL,
            'primary_use_case',
            NULL,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id) DO UPDATE SET
            onboarding_status = 'not_started',
            onboarding_version = excluded.onboarding_version,
            primary_use_case = NULL,
            onboarding_step = 'primary_use_case',
            household_usage_mode = NULL,
            onboarding_completed_at = NULL,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": normalized_household_id,
        "onboarding_version": ONBOARDING_VERSION,
    })
    return resolve_household_onboarding_state(conn, normalized_household_id)


def resolve_household_onboarding_state(conn, household_id: str) -> HouseholdOnboardingState:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    ensure_household_onboarding_foundation(conn)
    household_id_column, household_name_column = _household_registry_identity_columns(conn)
    row = conn.execute(text(f"""
        SELECT
            ho.household_id,
            hr.{household_name_column} AS household_name,
            ho.onboarding_status,
            ho.onboarding_version,
            ho.primary_use_case,
            ho.onboarding_step,
            ho.household_usage_mode,
            ho.onboarding_completed_at
        FROM household_onboarding ho
        JOIN household_registry hr
          ON CAST(hr.{household_id_column} AS TEXT) = ho.household_id
        WHERE ho.household_id = :household_id
        LIMIT 1
    """), {"household_id": normalized_household_id}).mappings().first()
    if not row:
        raise LookupError("Voor dit huishouden bestaat geen onboardingstatus")

    status = str(row.get("onboarding_status") or "").strip().lower()
    if status not in ONBOARDING_STATUSES:
        raise RuntimeError("Ongeldige onboardingstatus in database")

    primary_use_case = str(row.get("primary_use_case") or "").strip().lower() or None
    if primary_use_case is not None and primary_use_case not in PRIMARY_USE_CASES:
        raise RuntimeError("Ongeldig primair gebruiksdoel in database")

    household_usage_mode = str(row.get("household_usage_mode") or "").strip().lower() or None
    if household_usage_mode is not None and household_usage_mode not in HOUSEHOLD_USAGE_MODES:
        raise RuntimeError("Ongeldige alleen/samen-keuze in database")

    return HouseholdOnboardingState(
        household_id=str(row.get("household_id") or ""),
        household_name=str(row.get("household_name") or "").strip(),
        onboarding_status=status,
        onboarding_version=int(row.get("onboarding_version") or ONBOARDING_VERSION),
        primary_use_case=primary_use_case,
        onboarding_step=str(row.get("onboarding_step") or "").strip() or None,
        household_usage_mode=household_usage_mode,
        onboarding_completed_at=(
            str(row.get("onboarding_completed_at"))
            if row.get("onboarding_completed_at") is not None
            else None
        ),
    )


def select_primary_use_case(
    conn,
    *,
    household_id: str,
    primary_use_case: str,
) -> HouseholdOnboardingState:
    normalized_use_case = str(primary_use_case or "").strip().lower()
    if normalized_use_case not in PRIMARY_USE_CASES:
        raise ValueError("Ongeldig gebruiksdoel")

    current = resolve_household_onboarding_state(conn, household_id)
    if current.onboarding_status == ONBOARDING_STATUS_COMPLETED:
        raise OnboardingAlreadyCompletedError(
            "Dit huishouden heeft de initiële onboarding al afgerond"
        )

    conn.execute(text("""
        UPDATE household_onboarding
        SET primary_use_case = :primary_use_case,
            onboarding_status = 'in_progress',
            onboarding_step = :profile_follow_up_step,
            onboarding_version = :onboarding_version,
            updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id
    """), {
        "household_id": current.household_id,
        "primary_use_case": normalized_use_case,
        "profile_follow_up_step": PROFILE_FOLLOW_UP_STEP,
        "onboarding_version": ONBOARDING_VERSION,
    })
    return resolve_household_onboarding_state(conn, current.household_id)


def advance_profile_to_shared_household_minimum(
    conn,
    *,
    household_id: str,
    expected_primary_use_case: str,
) -> HouseholdOnboardingState:
    normalized_use_case = str(expected_primary_use_case or "").strip().lower()
    if normalized_use_case not in PRIMARY_USE_CASES:
        raise ValueError("Ongeldig gebruiksdoel")

    current = resolve_household_onboarding_state(conn, household_id)
    if current.onboarding_status == ONBOARDING_STATUS_COMPLETED:
        raise OnboardingAlreadyCompletedError(
            "Dit huishouden heeft de initiële onboarding al afgerond"
        )
    if (
        current.onboarding_status != ONBOARDING_STATUS_IN_PROGRESS
        or current.onboarding_step != PROFILE_FOLLOW_UP_STEP
        or current.primary_use_case != normalized_use_case
    ):
        raise ValueError("Onboarding staat niet op de verwachte profielstap")

    conn.execute(text("""
        UPDATE household_onboarding
        SET onboarding_status = 'in_progress',
            onboarding_step = :shared_household_minimum_step,
            onboarding_completed_at = NULL,
            onboarding_version = :onboarding_version,
            updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id
    """), {
        "household_id": current.household_id,
        "shared_household_minimum_step": SHARED_HOUSEHOLD_MINIMUM_STEP,
        "onboarding_version": ONBOARDING_VERSION,
    })
    return resolve_household_onboarding_state(conn, current.household_id)


def complete_household_onboarding(
    conn,
    *,
    household_id: str,
    household_name: str,
    household_usage_mode: str,
) -> HouseholdOnboardingState:
    normalized_name = _normalize_household_name(household_name)
    normalized_usage_mode = str(household_usage_mode or "").strip().lower()
    if normalized_usage_mode not in HOUSEHOLD_USAGE_MODES:
        raise ValueError("Kies of je Inhuis alleen of samen gebruikt")

    current = resolve_household_onboarding_state(conn, household_id)
    if current.onboarding_status == ONBOARDING_STATUS_COMPLETED:
        raise OnboardingAlreadyCompletedError(
            "Dit huishouden heeft de initiële onboarding al afgerond"
        )
    if (
        current.onboarding_status != ONBOARDING_STATUS_IN_PROGRESS
        or current.onboarding_step != SHARED_HOUSEHOLD_MINIMUM_STEP
        or current.primary_use_case not in PRIMARY_USE_CASES
    ):
        raise ValueError("Onboarding staat niet op de gedeelde huishoudstap")

    household_id_column, household_name_column = _household_registry_identity_columns(conn)
    result = conn.execute(text(f"""
        UPDATE household_registry
        SET {household_name_column} = :household_name
        WHERE CAST({household_id_column} AS TEXT) = :household_id
    """), {
        "household_id": current.household_id,
        "household_name": normalized_name,
    })
    if result.rowcount != 1:
        raise RuntimeError("Huishoudnaam kon niet eenduidig worden opgeslagen")

    conn.execute(text("""
        UPDATE household_onboarding
        SET onboarding_status = 'completed',
            onboarding_step = NULL,
            household_usage_mode = :household_usage_mode,
            onboarding_completed_at = CURRENT_TIMESTAMP,
            onboarding_version = :onboarding_version,
            updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id
    """), {
        "household_id": current.household_id,
        "household_usage_mode": normalized_usage_mode,
        "onboarding_version": ONBOARDING_VERSION,
    })
    return resolve_household_onboarding_state(conn, current.household_id)


def public_household_onboarding_payload(
    state: HouseholdOnboardingState,
    *,
    can_manage: bool,
) -> dict[str, Any]:
    return {
        "household_id": state.household_id,
        "household_name": state.household_name,
        "onboarding_status": state.onboarding_status,
        "onboarding_version": state.onboarding_version,
        "primary_use_case": state.primary_use_case,
        "onboarding_step": state.onboarding_step,
        "household_usage_mode": state.household_usage_mode,
        "initial_choice_required": state.initial_choice_required,
        "profile_follow_up_required": state.profile_follow_up_required,
        "shared_household_minimum_required": state.shared_household_minimum_required,
        "can_manage": bool(can_manage),
    }
