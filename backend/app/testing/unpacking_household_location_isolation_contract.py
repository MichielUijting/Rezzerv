from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import text

from app.services.inventory_location_household_patch import (
    validate_purchase_import_target_location_for_policy,
)
from app.services.unpacking_household_location_patch import (
    resolve_space_and_sublocation_ids,
    validate_purchase_import_target_location,
)
from app.testing.postgresql_acceptance_foundation import (
    create_postgresql_runtime_test_engine,
    postgresql_acceptance_snapshot,
    reset_postgresql_test_database,
)
from app.testing.postgresql_onboarding_selftest_fixture import seed_household


HOUSEHOLD_A = "unpacking-location-household-a"
HOUSEHOLD_B = "unpacking-location-household-b"
SYSTEM_HOUSEHOLD = "0"
PROVIDER_ID = "unpacking-location-provider"
PROVIDER_CODE = "unpacking-location-provider-code"


def _expect_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
        return
    raise AssertionError(f"Verwachte HTTP {status_code} bleef uit")


def _assert_postgresql_boolean_contract(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND (table_name, column_name) IN (
                  ('purchase_import_lines', 'is_auto_prefilled'),
                  ('spaces', 'active'),
                  ('sublocations', 'active')
              )
            ORDER BY table_name, column_name
            """
        )
    ).mappings().all()
    actual = {
        (str(row["table_name"]), str(row["column_name"])): str(row["data_type"])
        for row in rows
    }
    expected = {
        ("purchase_import_lines", "is_auto_prefilled"): "boolean",
        ("spaces", "active"): "boolean",
        ("sublocations", "active"): "boolean",
    }
    assert actual == expected, {"expected": expected, "actual": actual}


def _seed_provider(conn) -> str:
    provider_id = str(
        conn.execute(
            text(
                """
                INSERT INTO store_providers (
                    id, code, name, status, import_mode, created_at, updated_at
                ) VALUES (
                    :id, :code, :name, 'active', 'mock',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = 'active',
                    import_mode = 'mock',
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
            ),
            {
                "id": PROVIDER_ID,
                "code": PROVIDER_CODE,
                "name": "Uitpakken household location contract",
            },
        ).scalar_one()
    )
    return provider_id


def _seed_purchase_line(
    conn,
    *,
    household_id: str,
    provider_id: str,
    suffix: str,
    article_name: str,
) -> str:
    article_id = f"unpacking-location-article-{suffix}"
    connection_id = f"unpacking-location-connection-{suffix}"
    batch_id = f"unpacking-location-batch-{suffix}"
    line_id = f"unpacking-location-line-{suffix}"

    conn.execute(
        text(
            """
            INSERT INTO household_articles (
                id, household_id, naam, consumable, status, updated_at
            ) VALUES (
                :id, :household_id, :name, 1, 'active', CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": article_id,
            "household_id": household_id,
            "name": article_name,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO household_store_connections (
                id, household_id, store_provider_id, connection_status,
                linked_at, created_at, updated_at
            ) VALUES (
                :id, :household_id, :provider_id, 'active',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": connection_id,
            "household_id": household_id,
            "provider_id": provider_id,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_batches (
                id, household_id, store_provider_id, connection_id, source_type,
                source_reference, import_status, raw_payload, created_at
            ) VALUES (
                :id, :household_id, :provider_id, :connection_id, 'mock',
                :source_reference, 'in_review', :raw_payload, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": batch_id,
            "household_id": household_id,
            "provider_id": provider_id,
            "connection_id": connection_id,
            "source_reference": f"unpacking-location-contract:{suffix}",
            "raw_payload": json.dumps({"fixture": "unpacking-household-location-isolation"}),
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, external_article_code,
                article_name_raw, brand_raw, quantity_raw, unit_raw,
                line_price_raw, currency_code, match_status, review_decision,
                ui_sort_order, matched_household_article_id, target_location_id,
                processing_status, suggested_household_article_id,
                suggested_location_id, suggestion_confidence, suggestion_reason,
                is_auto_prefilled, article_override_mode, location_override_mode,
                created_at, updated_at
            ) VALUES (
                :id, :batch_id, :external_line_ref, :external_article_code,
                :article_name, '', 1, 'stuks',
                1.00, 'EUR', 'matched', 'selected',
                0, :article_id, NULL,
                'pending', :article_id,
                NULL, 'high', 'Uitpakken household location isolation contract',
                FALSE, 'auto', 'auto', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": line_id,
            "batch_id": batch_id,
            "external_line_ref": f"{suffix}-1",
            "external_article_code": f"UNPACKING-LOCATION-{suffix.upper()}",
            "article_name": article_name,
            "article_id": article_id,
        },
    )
    return line_id


def _prepare_database(engine) -> tuple[str, str]:
    reset_postgresql_test_database()

    with engine.begin() as conn:
        _assert_postgresql_boolean_contract(conn)

        seed_household(conn, household_id=HOUSEHOLD_A, name="Uitpakken huishouden A")
        seed_household(conn, household_id=HOUSEHOLD_B, name="Uitpakken huishouden B")
        seed_household(
            conn,
            household_id=SYSTEM_HOUSEHOLD,
            name="Systeemhuishouden",
            context_type="system",
        )

        provider_id = _seed_provider(conn)
        line_a = _seed_purchase_line(
            conn,
            household_id=HOUSEHOLD_A,
            provider_id=provider_id,
            suffix="a",
            article_name="Melk",
        )
        line_b = _seed_purchase_line(
            conn,
            household_id=HOUSEHOLD_B,
            provider_id=provider_id,
            suffix="b",
            article_name="Brood",
        )

        conn.execute(
            text(
                """
                INSERT INTO spaces (id, naam, household_id, active)
                VALUES
                    ('unpacking-space-a', 'Voorraadkast', :household_a, TRUE),
                    ('unpacking-space-b', 'Voorraadkast', :household_b, TRUE),
                    ('unpacking-space-zero', 'Systeemkast', :household_zero, TRUE)
                """
            ),
            {
                "household_a": HOUSEHOLD_A,
                "household_b": HOUSEHOLD_B,
                "household_zero": SYSTEM_HOUSEHOLD,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO sublocations (id, naam, space_id, active)
                VALUES
                    ('unpacking-sub-a', 'Boven', 'unpacking-space-a', TRUE),
                    ('unpacking-sub-b', 'Boven', 'unpacking-space-b', TRUE),
                    ('unpacking-sub-zero', 'Systeemplank', 'unpacking-space-zero', TRUE)
                """
            )
        )

        system_configuration_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM household_product_configuration
                    WHERE household_id = :household_id
                    """
                ),
                {"household_id": SYSTEM_HOUSEHOLD},
            ).scalar_one()
        )
        assert system_configuration_count == 0, system_configuration_count

    return line_a, line_b


def run_contract() -> None:
    snapshot = postgresql_acceptance_snapshot()
    assert snapshot["datastore"] == "postgresql", snapshot
    assert snapshot["runtime_create"] is False, snapshot

    engine = create_postgresql_runtime_test_engine()
    try:
        line_a, line_b = _prepare_database(engine)

        with engine.begin() as conn:
            runtime_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            assert runtime_user == "rezzerv_app", runtime_user

            resolved, line_ref = validate_purchase_import_target_location(
                conn,
                line_a,
                "unpacking-space-a",
            )
            assert resolved and resolved["space_id"] == "unpacking-space-a"
            assert line_ref["household_id"] == HOUSEHOLD_A

            resolved, _ = validate_purchase_import_target_location(
                conn,
                line_a,
                "unpacking-sub-a",
            )
            assert resolved and resolved["sublocation_id"] == "unpacking-sub-a"

            resolved, _ = validate_purchase_import_target_location(
                conn,
                line_a,
                "unpacking-space-b",
            )
            assert resolved is None
            resolved, _ = validate_purchase_import_target_location(
                conn,
                line_a,
                "unpacking-sub-b",
            )
            assert resolved is None

            resolved, line_b_ref = validate_purchase_import_target_location(
                conn,
                line_b,
                "unpacking-sub-b",
            )
            assert resolved and resolved["sublocation_id"] == "unpacking-sub-b"
            assert line_b_ref["household_id"] == HOUSEHOLD_B

            _expect_http_error(
                404,
                lambda: validate_purchase_import_target_location(
                    conn,
                    "missing-unpacking-line",
                    "unpacking-space-a",
                ),
            )

            # Systeemhuishouden 0 kan uit oudere data bestaan zonder
            # household_product_configuration. Een eigen terminale sublocatie moet
            # dan nog steeds veilig koppelbaar zijn, zonder cross-household fallback.
            legacy_zero_resolved, legacy_zero_error = (
                validate_purchase_import_target_location_for_policy(
                    conn,
                    SYSTEM_HOUSEHOLD,
                    "unpacking-sub-zero",
                )
            )
            assert legacy_zero_error is None
            assert legacy_zero_resolved
            assert legacy_zero_resolved["location_id"] == "unpacking-sub-zero"
            assert legacy_zero_resolved["space_id"] == "unpacking-space-zero"

            legacy_cross_resolved, legacy_cross_error = (
                validate_purchase_import_target_location_for_policy(
                    conn,
                    SYSTEM_HOUSEHOLD,
                    "unpacking-sub-b",
                )
            )
            assert legacy_cross_resolved is None
            assert legacy_cross_error

            legacy_parent_resolved, legacy_parent_error = (
                validate_purchase_import_target_location_for_policy(
                    conn,
                    SYSTEM_HOUSEHOLD,
                    "unpacking-space-zero",
                )
            )
            assert legacy_parent_resolved is None
            assert legacy_parent_error

            own_space, own_sub = resolve_space_and_sublocation_ids(
                conn,
                HOUSEHOLD_A,
                space_id="unpacking-space-a",
                sublocation_id="unpacking-sub-a",
            )
            assert own_space == "unpacking-space-a"
            assert own_sub == "unpacking-sub-a"

            _expect_http_error(
                400,
                lambda: resolve_space_and_sublocation_ids(
                    conn,
                    HOUSEHOLD_A,
                    space_id="unpacking-space-b",
                ),
            )
            _expect_http_error(
                400,
                lambda: resolve_space_and_sublocation_ids(
                    conn,
                    HOUSEHOLD_A,
                    sublocation_id="unpacking-sub-b",
                ),
            )
            _expect_http_error(
                400,
                lambda: resolve_space_and_sublocation_ids(
                    conn,
                    None,
                    space_name="Onveilig",
                ),
            )

            new_space, new_sub = resolve_space_and_sublocation_ids(
                conn,
                HOUSEHOLD_A,
                space_name="Koele berging",
                sublocation_name="Onderste plank",
            )
            created = conn.execute(
                text(
                    """
                    SELECT s.household_id, sl.id AS sublocation_id
                    FROM spaces s
                    JOIN sublocations sl ON sl.space_id = s.id
                    WHERE s.id = :space_id
                      AND sl.id = :sublocation_id
                    """
                ),
                {"space_id": new_space, "sublocation_id": new_sub},
            ).mappings().one()
            assert created["household_id"] == HOUSEHOLD_A

            b_counts = conn.execute(
                text(
                    """
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM spaces
                            WHERE household_id = :household_b
                        ) AS spaces,
                        (
                            SELECT COUNT(*)
                            FROM sublocations sl
                            JOIN spaces s ON s.id = sl.space_id
                            WHERE s.household_id = :household_b
                        ) AS sublocations
                    """
                ),
                {"household_b": HOUSEHOLD_B},
            ).mappings().one()
            assert int(b_counts["spaces"]) == 1
            assert int(b_counts["sublocations"]) == 1

        print("PASS postgresql_dml_only_runtime")
        print("PASS household_a_b_location_isolation")
        print("PASS system_household_zero_without_product_configuration")
        print("PASS cross_household_location_rejected")
        print("UNPACKING_HOUSEHOLD_LOCATION_ISOLATION_GREEN")
    finally:
        engine.dispose()


if __name__ == "__main__":
    run_contract()
