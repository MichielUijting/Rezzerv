from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import bindparam, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app import main

HOUSEHOLD_ID = "0"


def _ensure_household_zero_parent() -> None:
    with main.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, context_type, created_at)
                VALUES (:id, :naam, 'system', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    context_type = 'system'
                """
            ),
            {
                "id": HOUSEHOLD_ID,
                "naam": "Regressietest huishouden 0",
            },
        )


def _portable_ensure_regression_inventory_fixture(household_id: str) -> dict:
    normalized_household_id = str(household_id or "").strip() or "1"
    with main.engine.begin() as conn:
        space_id = conn.execute(
            text(
                "SELECT id FROM spaces "
                "WHERE household_id = :household_id "
                "AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"
            ),
            {
                "household_id": normalized_household_id,
                "naam": main.REGRESSION_FIXTURE_SPACE_NAME,
            },
        ).scalar()
        if not space_id:
            space_id = uuid.uuid4().hex
            conn.execute(
                text(
                    "INSERT INTO spaces (id, naam, household_id) "
                    "VALUES (:id, :naam, :household_id)"
                ),
                {
                    "id": space_id,
                    "naam": main.REGRESSION_FIXTURE_SPACE_NAME,
                    "household_id": normalized_household_id,
                },
            )

        sublocation_id = conn.execute(
            text(
                "SELECT id FROM sublocations "
                "WHERE space_id = :space_id "
                "AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"
            ),
            {
                "space_id": space_id,
                "naam": main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
            },
        ).scalar()
        if not sublocation_id:
            sublocation_id = uuid.uuid4().hex
            conn.execute(
                text(
                    "INSERT INTO sublocations (id, naam, space_id) "
                    "VALUES (:id, :naam, :space_id)"
                ),
                {
                    "id": sublocation_id,
                    "naam": main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
                    "space_id": space_id,
                },
            )

        conn.execute(
            text(
                "DELETE FROM inventory_events "
                "WHERE household_id = :household_id "
                "AND (source = 'regression_fixture' OR note = :note)"
            ),
            {
                "household_id": normalized_household_id,
                "note": main.REGRESSION_FIXTURE_NOTE,
            },
        )
        conn.execute(
            text(
                """
                DELETE FROM inventory
                WHERE household_id = :household_id
                  AND (
                    archive_reason = :note
                    OR (
                      COALESCE(space_id, '') = COALESCE(:space_id, '')
                      AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
                      AND lower(trim(naam)) = lower(trim(:article_name))
                    )
                  )
                """
            ),
            {
                "household_id": normalized_household_id,
                "note": main.REGRESSION_FIXTURE_NOTE,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
                "article_name": main.REGRESSION_FIXTURE_ARTICLE_NAME,
            },
        )

        ensured_article_option_id = main.ensure_household_article(
            conn,
            normalized_household_id,
            main.REGRESSION_FIXTURE_ARTICLE_NAME,
        )
        household_article_row = main.get_household_article_row_by_name(
            conn,
            normalized_household_id,
            main.REGRESSION_FIXTURE_ARTICLE_NAME,
        )
        household_article_id = (
            str(household_article_row.get("id") or "").strip()
            if household_article_row
            else ""
        )

        inventory_id = uuid.uuid4().hex
        conn.execute(
            text(
                """
                INSERT INTO inventory
                    (id, naam, aantal, household_id, space_id, sublocation_id, status, updated_at)
                VALUES
                    (:id, :naam, 1, :household_id, :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": inventory_id,
                "naam": main.REGRESSION_FIXTURE_ARTICLE_NAME,
                "household_id": normalized_household_id,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
            },
        )
        main.create_inventory_event(
            conn,
            household_id=normalized_household_id,
            article_id=inventory_id,
            article_name=main.REGRESSION_FIXTURE_ARTICLE_NAME,
            resolved_location={
                "location_id": sublocation_id or space_id,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
                "location_label": " / ".join(
                    part
                    for part in [
                        main.REGRESSION_FIXTURE_SPACE_NAME,
                        main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
                    ]
                    if part
                ),
            },
            event_type="purchase",
            quantity=1,
            source="regression_fixture",
            note=main.REGRESSION_FIXTURE_NOTE,
            old_quantity=0,
            new_quantity=1,
        )

    payload = {
        "articleId": household_article_id or str(inventory_id),
        "householdArticleId": household_article_id or None,
        "inventoryId": str(inventory_id),
        "articleOptionId": ensured_article_option_id,
        "articleName": main.REGRESSION_FIXTURE_ARTICLE_NAME,
        "spaceName": main.REGRESSION_FIXTURE_SPACE_NAME,
        "sublocationName": main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
        "spaceId": str(space_id),
        "sublocationId": str(sublocation_id),
    }
    main.log_regression_action(
        "fixture.ensure_inventory",
        household_id=normalized_household_id,
        **payload,
    )
    return payload


def _portable_cleanup_regression_inventory_state(household_id: str) -> dict:
    normalized_household_id = str(household_id or "").strip() or "1"
    normalized_fixture_names = [
        name.strip().lower()
        for name in main.REGRESSION_ARTICLE_NAMES
        if str(name or "").strip()
    ]

    with main.engine.begin() as conn:
        fixture_space_id = conn.execute(
            text(
                "SELECT id FROM spaces "
                "WHERE household_id = :household_id "
                "AND lower(trim(naam)) = lower(trim(:space_name)) LIMIT 1"
            ),
            {
                "household_id": normalized_household_id,
                "space_name": main.REGRESSION_FIXTURE_SPACE_NAME,
            },
        ).scalar()
        fixture_sublocation_id = None
        if fixture_space_id:
            fixture_sublocation_id = conn.execute(
                text(
                    "SELECT id FROM sublocations "
                    "WHERE space_id = :space_id "
                    "AND lower(trim(naam)) = lower(trim(:sublocation_name)) LIMIT 1"
                ),
                {
                    "space_id": fixture_space_id,
                    "sublocation_name": main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
                },
            ).scalar()

        conn.execute(
            text(
                "DELETE FROM inventory_events "
                "WHERE household_id = :household_id "
                "AND (source = 'regression_fixture' OR note = :note)"
            ),
            {
                "household_id": normalized_household_id,
                "note": main.REGRESSION_FIXTURE_NOTE,
            },
        )

        if fixture_space_id:
            conn.execute(
                text(
                    """
                    DELETE FROM inventory
                    WHERE household_id = :household_id
                      AND (
                        archive_reason = :note
                        OR (
                          COALESCE(space_id, '') = :space_id
                          AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
                          AND lower(trim(naam)) IN :names
                        )
                      )
                    """
                ).bindparams(bindparam("names", expanding=True)),
                {
                    "household_id": normalized_household_id,
                    "note": main.REGRESSION_FIXTURE_NOTE,
                    "space_id": fixture_space_id,
                    "sublocation_id": fixture_sublocation_id,
                    "names": normalized_fixture_names,
                },
            )
        else:
            conn.execute(
                text(
                    "DELETE FROM inventory "
                    "WHERE household_id = :household_id "
                    "AND archive_reason = :note"
                ),
                {
                    "household_id": normalized_household_id,
                    "note": main.REGRESSION_FIXTURE_NOTE,
                },
            )

        conn.execute(
            text(
                "DELETE FROM sublocations WHERE id IN ("
                "SELECT sl.id FROM sublocations sl "
                "JOIN spaces s ON s.id = sl.space_id "
                "WHERE s.household_id = :household_id "
                "AND lower(trim(s.naam)) = lower(:space_name) "
                "AND lower(trim(sl.naam)) = lower(:sublocation_name))"
            ),
            {
                "household_id": normalized_household_id,
                "space_name": main.REGRESSION_FIXTURE_SPACE_NAME,
                "sublocation_name": main.REGRESSION_FIXTURE_SUBLOCATION_NAME,
            },
        )
        conn.execute(
            text(
                "DELETE FROM spaces "
                "WHERE household_id = :household_id "
                "AND lower(trim(naam)) = lower(:space_name) "
                "AND id NOT IN (SELECT DISTINCT space_id FROM inventory WHERE space_id IS NOT NULL)"
            ),
            {
                "household_id": normalized_household_id,
                "space_name": main.REGRESSION_FIXTURE_SPACE_NAME,
            },
        )
        inventory_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM inventory "
                "WHERE household_id = :household_id "
                "AND COALESCE(status, 'active') = 'active' "
                "AND COALESCE(aantal, 0) > 0"
            ),
            {"household_id": normalized_household_id},
        ).scalar() or 0
        history_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM inventory_events "
                "WHERE household_id = :household_id"
            ),
            {"household_id": normalized_household_id},
        ).scalar() or 0

    payload = {
        "inventory_count": int(inventory_count),
        "history_count": int(history_count),
    }
    main.log_regression_action(
        "fixture.cleanup_inventory",
        household_id=normalized_household_id,
        **payload,
    )
    return payload


def _with_household_zero_overrides(action):
    original_require_platform_admin_user = main.require_platform_admin_user
    original_ensure_household = main.ensure_household
    original_ensure_regression_inventory_fixture = main.ensure_regression_inventory_fixture
    original_cleanup_regression_inventory_state = main.cleanup_regression_inventory_state
    try:
        main.require_platform_admin_user = lambda _authorization=None: {
            "email": "supergebruiker@rezzerv.local"
        }
        main.ensure_household = lambda _email: {
            "id": HOUSEHOLD_ID,
            "naam": "Regressietest huishouden 0",
        }
        main.ensure_regression_inventory_fixture = _portable_ensure_regression_inventory_fixture
        main.cleanup_regression_inventory_state = _portable_cleanup_regression_inventory_state
        return action()
    finally:
        main.require_platform_admin_user = original_require_platform_admin_user
        main.ensure_household = original_ensure_household
        main.ensure_regression_inventory_fixture = original_ensure_regression_inventory_fixture
        main.cleanup_regression_inventory_state = original_cleanup_regression_inventory_state


def prepare() -> dict:
    def action():
        _ensure_household_zero_parent()
        reset = main.reset_regression_fixture_state()
        receipts = main.seed_regression_kassa_receipts(authorization=None)
        return {
            "status": "ok",
            "mode": "prepare",
            "household_id": HOUSEHOLD_ID,
            "reset": reset,
            "receipts": receipts,
        }

    result = _with_household_zero_overrides(action)
    if str(result.get("reset", {}).get("household_id")) != HOUSEHOLD_ID:
        raise RuntimeError(f"Reset gebruikte niet huishouden {HOUSEHOLD_ID}: {result}")
    if str(result.get("receipts", {}).get("household_id")) != HOUSEHOLD_ID:
        raise RuntimeError(f"Kassabonseed gebruikte niet huishouden {HOUSEHOLD_ID}: {result}")
    return result


def cleanup() -> dict:
    result = _with_household_zero_overrides(
        lambda: main.cleanup_regression_fixture_state(HOUSEHOLD_ID)
    )
    return {
        "status": "ok",
        "mode": "cleanup",
        "household_id": HOUSEHOLD_ID,
        **result,
    }


def main_entry() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "prepare":
        result = prepare()
    elif mode == "cleanup":
        result = cleanup()
    else:
        raise RuntimeError("Gebruik: household_zero_regression_fixture.py prepare|cleanup")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    print(f"HOUSEHOLD_ZERO_FIXTURE_{mode.upper()}=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
