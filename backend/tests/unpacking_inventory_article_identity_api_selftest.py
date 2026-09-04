"""P0 F3-03: Uitpakken -> inventory -> household article identity on PostgreSQL.

This is the real L3 API authority for the purchase-import processing path. It
uses the production FastAPI routes, canonical authorization/object guard and a
DML-only PostgreSQL runtime. The test proves that two purchases of the same
article converge on one household_articles identity and that purchase lines,
inventory rows and inventory_events keep that identity end-to-end. It also
proves that another household cannot mutate or process the target household's
Uitpakken objects.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

TARGET_HOUSEHOLD = "f3-unpacking-target"
ISOLATION_HOUSEHOLD = "f3-unpacking-isolation"
TARGET_ADMIN_EMAIL = "f3-unpacking-admin@rezzerv.local"
ISOLATION_ADMIN_EMAIL = "f3-unpacking-isolation-admin@rezzerv.local"
SEED_PASSWORD = "F3UnpackingSeed123!"
ARTICLE_NAME = "F3 Canonical voorraadartikel"
SPACE_NAME = "F3 Voorraadruimte"
SUBLOCATION_NAME = "F3 Voorraadplank"


def _headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer rezzerv-dev-token::{email.lower()}"}


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id=TARGET_HOUSEHOLD,
        household_name="F3 Uitpakken doelhuishouden",
        admin_id="f3-unpacking-admin",
        admin_email=TARGET_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-unpacking-admin-membership",
        member_id="f3-unpacking-member",
        member_email="f3-unpacking-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-unpacking-member-membership",
    )
    seed_admin_member_household(
        engine,
        household_id=ISOLATION_HOUSEHOLD,
        household_name="F3 Uitpakken isolatiehuishouden",
        admin_id="f3-unpacking-isolation-admin",
        admin_email=ISOLATION_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-unpacking-isolation-admin-membership",
        member_id="f3-unpacking-isolation-member",
        member_email="f3-unpacking-isolation-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-unpacking-isolation-member-membership",
    )


def _pull_batch(client: TestClient, connection_id: str, owner_headers: dict[str, str]) -> tuple[str, list[dict]]:
    pulled = client.post(
        f"/api/store-connections/{connection_id}/pull-purchases",
        headers=owner_headers,
        json={"mock_profile": "default"},
    )
    assert pulled.status_code == 200, pulled.text
    batch_id = str(pulled.json()["batch_id"])

    loaded = client.get(
        f"/api/purchase-import-batches/{batch_id}",
        headers=owner_headers,
    )
    assert loaded.status_code == 200, loaded.text
    lines = list(loaded.json().get("lines") or [])
    assert lines, loaded.text
    return batch_id, lines


def _keep_only_line(client: TestClient, lines: list[dict], chosen_line_id: str, owner_headers: dict[str, str]) -> None:
    for line in lines:
        line_id = str(line["id"])
        decision = "selected" if line_id == chosen_line_id else "ignored"
        response = client.post(
            f"/api/purchase-import-lines/{line_id}/review",
            headers=owner_headers,
            json={"review_decision": decision},
        )
        assert response.status_code == 200, response.text


def _set_target_location(client: TestClient, line_id: str, location_id: str, headers: dict[str, str]) -> None:
    response = client.post(
        f"/api/purchase-import-lines/{line_id}/target-location",
        headers=headers,
        json={"target_location_id": location_id, "default_location_policy": "line_only"},
    )
    assert response.status_code == 200, response.text
    assert str(response.json().get("target_location_id") or "") == location_id


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            runtime_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )
            assert runtime_create is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)

        # Import after the canonical schema and auth fixtures are ready. The production
        # module reads DATABASE_URL from the same runtime boundary; assigning the
        # already verified engine makes that authority explicit for this selftest.
        from app import main as main_module

        main_module.engine = engine
        owner_headers = _headers(TARGET_ADMIN_EMAIL)
        isolation_headers = _headers(ISOLATION_ADMIN_EMAIL)

        with TestClient(main_module.app) as client:
            created_space = client.post(
                "/api/spaces",
                headers=owner_headers,
                json={"household_id": TARGET_HOUSEHOLD, "naam": SPACE_NAME, "active": True},
            )
            assert created_space.status_code == 200, created_space.text
            space_id = str(created_space.json()["space"]["id"])
            assert space_id

            created_sublocation = client.post(
                "/api/sublocations",
                headers=owner_headers,
                json={"space_id": space_id, "naam": SUBLOCATION_NAME, "active": True},
            )
            assert created_sublocation.status_code == 200, created_sublocation.text
            location_id = str(created_sublocation.json()["sublocation"]["id"])
            assert location_id

            with engine.begin() as conn:
                location_row = conn.execute(
                    text(
                        """
                        SELECT sl.id, sl.space_id, s.household_id
                        FROM sublocations sl
                        JOIN spaces s ON s.id = sl.space_id
                        WHERE sl.id = :location_id
                        """
                    ),
                    {"location_id": location_id},
                ).mappings().one()
                assert str(location_row["space_id"]) == space_id
                assert str(location_row["household_id"]) == TARGET_HOUSEHOLD
            checks.append("target_location_is_persisted_in_target_household")

            connection = client.post(
                "/api/store-connections",
                headers=owner_headers,
                json={"household_id": TARGET_HOUSEHOLD, "store_provider_code": "jumbo"},
            )
            assert connection.status_code == 200, connection.text
            connection_id = str(connection.json()["id"])
            assert connection_id

            batch1_id, batch1_lines = _pull_batch(client, connection_id, owner_headers)
            line1_id = str(batch1_lines[0]["id"])
            _keep_only_line(client, batch1_lines, line1_id, owner_headers)

            created_article = client.post(
                f"/api/purchase-import-lines/{line1_id}/create-article",
                headers=owner_headers,
                json={"article_name": ARTICLE_NAME},
            )
            assert created_article.status_code == 200, created_article.text
            article_id = str(created_article.json()["matched_household_article_id"])
            assert article_id
            _set_target_location(client, line1_id, location_id, owner_headers)

            processed1 = client.post(
                f"/api/purchase-import-batches/{batch1_id}/process",
                headers=owner_headers,
                json={"mode": "selected_only", "processed_by": "f3-03"},
            )
            assert processed1.status_code == 200, processed1.text
            result1 = processed1.json()
            assert result1["processed_count"] == 1, result1
            assert result1["failed_count"] == 0, result1
            assert result1["status"] in {"processed", "partially_processed"}, result1

            with engine.begin() as conn:
                line1 = conn.execute(
                    text(
                        """
                        SELECT matched_household_article_id, processing_status, processed_event_id,
                               target_location_id, final_location_id, quantity_raw
                        FROM purchase_import_lines
                        WHERE id = :line_id
                        """
                    ),
                    {"line_id": line1_id},
                ).mappings().one()
                assert str(line1["matched_household_article_id"]) == article_id
                assert line1["processing_status"] == "processed"
                event1_id = str(line1["processed_event_id"] or "")
                assert event1_id
                assert str(line1["target_location_id"]) == location_id
                assert str(line1["final_location_id"]) == location_id

                article1 = conn.execute(
                    text(
                        """
                        SELECT id, household_id, COALESCE(custom_name, naam) AS display_name
                        FROM household_articles
                        WHERE id = :article_id
                        """
                    ),
                    {"article_id": article_id},
                ).mappings().one()
                assert str(article1["household_id"]) == TARGET_HOUSEHOLD
                assert str(article1["display_name"]).strip().lower() == ARTICLE_NAME.lower()

                inventory1 = conn.execute(
                    text(
                        """
                        SELECT id, household_article_id, household_id, aantal, space_id, sublocation_id
                        FROM inventory
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND COALESCE(status, 'active') = 'active'
                        """
                    ),
                    {"household_id": TARGET_HOUSEHOLD, "article_id": article_id},
                ).mappings().all()
                assert inventory1
                assert all(str(row["household_article_id"]) == article_id for row in inventory1)
                assert all(str(row["household_id"]) == TARGET_HOUSEHOLD for row in inventory1)
                assert any(str(row["sublocation_id"] or "") == location_id for row in inventory1)
                total_after_first = sum(int(row["aantal"] or 0) for row in inventory1)
                assert total_after_first > 0

                event1 = conn.execute(
                    text(
                        """
                        SELECT id, household_id, household_article_id
                        FROM inventory_events
                        WHERE id = :event_id
                        """
                    ),
                    {"event_id": event1_id},
                ).mappings().one()
                assert str(event1["household_id"]) == TARGET_HOUSEHOLD
                assert str(event1["household_article_id"]) == article_id
            checks.append("first_unpack_process_persists_one_canonical_article_identity")

            batch2_id, batch2_lines = _pull_batch(client, connection_id, owner_headers)
            line2_id = str(batch2_lines[0]["id"])
            _keep_only_line(client, batch2_lines, line2_id, owner_headers)

            # The object guard must run before the mutation route itself. A foreign
            # household admin must not be able to attach even a valid target-household
            # location to the target household's import line.
            forbidden_location = client.post(
                f"/api/purchase-import-lines/{line2_id}/target-location",
                headers=isolation_headers,
                json={"target_location_id": location_id, "default_location_policy": "line_only"},
            )
            assert forbidden_location.status_code == 403, forbidden_location.text

            mapped = client.post(
                f"/api/purchase-import-lines/{line2_id}/map",
                headers=owner_headers,
                json={"household_article_id": article_id},
            )
            assert mapped.status_code == 200, mapped.text
            assert str(mapped.json().get("matched_household_article_id") or "") == article_id
            _set_target_location(client, line2_id, location_id, owner_headers)

            with engine.begin() as conn:
                pre_forbidden = conn.execute(
                    text(
                        """
                        SELECT processing_status, processed_event_id
                        FROM purchase_import_lines
                        WHERE id = :line_id
                        """
                    ),
                    {"line_id": line2_id},
                ).mappings().one()
                assert pre_forbidden["processing_status"] != "processed"
                assert pre_forbidden["processed_event_id"] is None

            forbidden_process = client.post(
                f"/api/purchase-import-batches/{batch2_id}/process",
                headers=isolation_headers,
                json={"mode": "selected_only", "processed_by": "foreign-household"},
            )
            assert forbidden_process.status_code == 403, forbidden_process.text

            with engine.begin() as conn:
                after_forbidden = conn.execute(
                    text(
                        """
                        SELECT processing_status, processed_event_id
                        FROM purchase_import_lines
                        WHERE id = :line_id
                        """
                    ),
                    {"line_id": line2_id},
                ).mappings().one()
                assert after_forbidden["processing_status"] != "processed"
                assert after_forbidden["processed_event_id"] is None
            checks.append("cross_household_unpack_mutation_and_processing_are_blocked")

            processed2 = client.post(
                f"/api/purchase-import-batches/{batch2_id}/process",
                headers=owner_headers,
                json={"mode": "selected_only", "processed_by": "f3-03"},
            )
            assert processed2.status_code == 200, processed2.text
            result2 = processed2.json()
            assert result2["processed_count"] == 1, result2
            assert result2["failed_count"] == 0, result2

            with engine.begin() as conn:
                line2 = conn.execute(
                    text(
                        """
                        SELECT matched_household_article_id, processing_status, processed_event_id
                        FROM purchase_import_lines
                        WHERE id = :line_id
                        """
                    ),
                    {"line_id": line2_id},
                ).mappings().one()
                assert str(line2["matched_household_article_id"]) == article_id
                assert line2["processing_status"] == "processed"
                event2_id = str(line2["processed_event_id"] or "")
                assert event2_id and event2_id != event1_id

                canonical_count = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM household_articles
                            WHERE household_id = :household_id
                              AND lower(trim(COALESCE(custom_name, naam))) = lower(trim(:article_name))
                            """
                        ),
                        {"household_id": TARGET_HOUSEHOLD, "article_name": ARTICLE_NAME},
                    ).scalar_one()
                )
                assert canonical_count == 1

                target_inventory = conn.execute(
                    text(
                        """
                        SELECT household_article_id, household_id, aantal
                        FROM inventory
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND COALESCE(status, 'active') = 'active'
                        """
                    ),
                    {"household_id": TARGET_HOUSEHOLD, "article_id": article_id},
                ).mappings().all()
                assert target_inventory
                total_after_second = sum(int(row["aantal"] or 0) for row in target_inventory)
                assert total_after_second > total_after_first
                assert all(str(row["household_article_id"]) == article_id for row in target_inventory)

                purchase_events = conn.execute(
                    text(
                        """
                        SELECT id, household_id, household_article_id
                        FROM inventory_events
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND id IN (:event1_id, :event2_id)
                        ORDER BY id
                        """
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "article_id": article_id,
                        "event1_id": event1_id,
                        "event2_id": event2_id,
                    },
                ).mappings().all()
                assert len(purchase_events) == 2, purchase_events
                assert {str(row["id"]) for row in purchase_events} == {event1_id, event2_id}
                assert all(str(row["household_article_id"]) == article_id for row in purchase_events)

                isolation_article_rows = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM household_articles
                            WHERE household_id = :household_id
                              AND id = :article_id
                            """
                        ),
                        {"household_id": ISOLATION_HOUSEHOLD, "article_id": article_id},
                    ).scalar_one()
                )
                isolation_inventory_rows = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM inventory
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                            """
                        ),
                        {"household_id": ISOLATION_HOUSEHOLD, "article_id": article_id},
                    ).scalar_one()
                )
                isolation_event_rows = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM inventory_events
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                            """
                        ),
                        {"household_id": ISOLATION_HOUSEHOLD, "article_id": article_id},
                    ).scalar_one()
                )
                assert isolation_article_rows == 0
                assert isolation_inventory_rows == 0
                assert isolation_event_rows == 0
            checks.append("repeat_unpack_reuses_identity_and_accumulates_inventory")
            checks.append("postgresql_end_state_preserves_household_article_identity_and_isolation")

            replay = client.post(
                f"/api/purchase-import-batches/{batch2_id}/process",
                headers=owner_headers,
                json={"mode": "selected_only", "processed_by": "f3-03-replay"},
            )
            assert replay.status_code == 200, replay.text
            assert replay.json()["processed_count"] == 1
            with engine.begin() as conn:
                replay_event_count = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM inventory_events
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                              AND id = :event2_id
                            """
                        ),
                        {
                            "household_id": TARGET_HOUSEHOLD,
                            "article_id": article_id,
                            "event2_id": event2_id,
                        },
                    ).scalar_one()
                )
                assert replay_event_count == 1
                replay_inventory_total = int(
                    conn.execute(
                        text(
                            """
                            SELECT COALESCE(SUM(aantal), 0)
                            FROM inventory
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                              AND COALESCE(status, 'active') = 'active'
                            """
                        ),
                        {"household_id": TARGET_HOUSEHOLD, "article_id": article_id},
                    ).scalar_one()
                )
                assert replay_inventory_total == total_after_second
            checks.append("processed_batch_replay_is_idempotent")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("UNPACKING_INVENTORY_ARTICLE_IDENTITY_API_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
