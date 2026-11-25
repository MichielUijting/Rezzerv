"""Durable, household-scoped first-store onboarding without retailer credentials.

Only new regular households are seeded by quick-start. A success requires
server-side proof: an AH account credential or a staged retailer receipt.
This is separate from the canonical receipt-import status authority.
"""
from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import text

STORE_CODES = ("ah", "jumbo", "lidl")
SETTING_KEY = "first_store_onboarding_v1"
RESULTS = frozenset({"success", "failed"})


def _empty_state(*, available: bool = False) -> dict:
    return {"available": available, "selected": [], "results": {}}


def _read(conn, household_id: str) -> dict:
    raw = conn.execute(text("""
        SELECT setting_value FROM household_settings
        WHERE household_id = :household_id AND setting_key = :setting_key
    """), {"household_id": household_id, "setting_key": SETTING_KEY}).scalar_one_or_none()
    if raw is None:
        return _empty_state()
    try:
        data = json.loads(raw)
        selected = data["selected"]
        results = data["results"]
        if not isinstance(selected, list) or not isinstance(results, dict):
            raise ValueError("Invalid store onboarding state")
        if len(set(selected)) != len(selected) or any(code not in STORE_CODES for code in selected):
            raise ValueError("Invalid store onboarding selection")
        if any(code not in selected or result not in RESULTS for code, result in results.items()):
            raise ValueError("Invalid store onboarding result")
    except (TypeError, KeyError, ValueError) as exc:
        raise RuntimeError("Ongeldige opgeslagen winkelonboarding; geen automatische reset.") from exc
    return {"available": True, "selected": selected, "results": results}


def read_store_onboarding(conn, household_id: str) -> dict:
    """Never seed legacy households or change data on a read."""
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Regulier huishouden vereist")
    return _read(conn, owner)


def seed_store_onboarding(conn, household_id: str) -> None:
    """Called inside the same registration/quick-start transaction."""
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Regulier huishouden vereist")
    conn.execute(text("""
        INSERT INTO household_settings
          (id, household_id, setting_key, setting_value, updated_at)
        VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
        ON CONFLICT (household_id, setting_key) DO NOTHING
    """), {
        "id": uuid4().hex, "household_id": owner, "setting_key": SETTING_KEY,
        "setting_value": json.dumps({"selected": [], "results": {}}, sort_keys=True),
    })


def _write(conn, household_id: str, state: dict) -> dict:
    result = conn.execute(text("""
        UPDATE household_settings
        SET setting_value = :setting_value, updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id AND setting_key = :setting_key
    """), {
        "household_id": household_id, "setting_key": SETTING_KEY,
        "setting_value": json.dumps({
            "selected": state["selected"], "results": state["results"],
        }, sort_keys=True, separators=(",", ":")),
    })
    if result.rowcount != 1:
        raise RuntimeError("Winkelonboarding kon niet veilig worden opgeslagen")
    return state


def update_store_selection(conn, household_id: str, selected: list[str]) -> dict:
    owner = str(household_id or "").strip()
    state = read_store_onboarding(conn, owner)
    if not state["available"]:
        raise ValueError("Deze winkelonboarding is niet actief voor dit huishouden")
    if len(selected) != len(set(selected)) or any(code not in STORE_CODES for code in selected):
        raise ValueError("Ongeldige winkelkeuze")
    # A confirmed success cannot be silently removed or retried.
    successes = {code for code, result in state["results"].items() if result == "success"}
    if not successes.issubset(selected):
        raise ValueError("Een geslaagde koppeling kan hier niet worden verwijderd")
    state["selected"] = [code for code in STORE_CODES if code in selected]
    state["results"] = {code: result for code, result in state["results"].items() if code in selected}
    return _write(conn, owner, state)


def record_store_result(
    conn, household_id: str, *, provider: str, result: str,
    queue_id: str | None = None,
) -> dict:
    owner = str(household_id or "").strip()
    state = read_store_onboarding(conn, owner)
    if not state["available"] or provider not in state["selected"]:
        raise ValueError("Kies deze winkel eerst tijdens de onboarding")
    if result not in RESULTS or provider not in STORE_CODES:
        raise ValueError("Ongeldig winkelresultaat")
    if state["results"].get(provider) == "success":
        return state
    if result == "success":
        if provider == "ah":
            proof = conn.execute(text("""
                SELECT 1 FROM retailer_account_credentials
                WHERE household_id = :household_id AND provider = 'ah' LIMIT 1
            """), {"household_id": owner}).scalar_one_or_none()
        else:
            if not queue_id:
                raise ValueError("Een bevestigde winkelbon ontbreekt")
            proof = conn.execute(text("""
                SELECT 1 FROM retailer_import_queue
                WHERE household_id = :household_id AND provider = :provider
                  AND id = :queue_id LIMIT 1
            """), {
                "household_id": owner, "provider": provider, "queue_id": queue_id,
            }).scalar_one_or_none()
        if proof is None:
            raise ValueError("De koppeling of bonontvangst is nog niet door Inhuis bevestigd")
    state["results"][provider] = result
    return _write(conn, owner, state)
