from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
)
from app.services.purchase_import_location_policy_patch import (
    _policy_store_storage_target_location,
    _processing_household_id,
    classify_locationless_ready_line,
    is_locationless_bulk_candidate,
    recover_explicit_approved_receipt_article_link,
    install_purchase_import_location_policy_patch,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
)


@pytest.fixture
def engine():
    reset_postgresql_test_database()
    test_engine = create_postgresql_runtime_test_engine()
    try:
        yield test_engine
    finally:
        test_engine.dispose()


def _seed_location_policy(conn):
    ensure_household_product_configuration_foundation(conn)
    seed_household(
        conn,
        household_id="house-none",
        name="Zonder locaties",
    )
    conn.execute(text("""
        INSERT INTO household_product_configuration (
            household_id,
            inventory_tracking_level,
            location_tracking_level,
            shopping_enabled,
            almost_out_enabled,
            almost_out_notifications_enabled,
            receipt_processing_enabled,
            recipes_enabled,
            unpacking_enabled
        ) VALUES (
            'house-none', 'quantity', 'none', 1, 0, 0, 1, 0, 0
        )
    """))
    conn.execute(text("""
        INSERT INTO spaces (id, naam, household_id, active)
        VALUES ('legacy-space', 'Oude ruimte', 'house-none', TRUE)
    """))


def test_locationless_ready_only_ignores_missing_location_but_not_other_requirements():
    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": "article-1",
        "matched_global_product_id": None,
        "selected_article_group_id": "group-1",
        "target_location_id": None,
    })
    assert ready is True
    assert reason is None
    assert stage is None

    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": None,
        "matched_global_product_id": "product-1",
        "selected_article_group_id": "group-1",
        "target_location_id": None,
    })
    assert ready is True

    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": None,
        "matched_global_product_id": None,
        "selected_article_group_id": "group-1",
        "target_location_id": None,
    })
    assert ready is False
    assert reason == "Nog geen artikel of product gekoppeld"
    assert stage == "article_resolution"

    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": "article-1",
        "matched_global_product_id": None,
        "selected_article_group_id": None,
        "target_location_id": None,
    })
    assert (ready, reason, stage) == (True, None, None)


def test_locationless_ready_only_accepts_a_legacy_receipt_location():
    # Switching the current household policy must not require editing every
    # previously imported receipt line. The original line remains unchanged.
    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": "article-1",
        "matched_global_product_id": None,
        "selected_article_group_id": "group-1",
        "target_location_id": "legacy-space",
    })
    assert (ready, reason, stage) == (True, None, None)


def test_locationless_bulk_candidates_only_include_approved_pending_or_explicit_selected():
    assert is_locationless_bulk_candidate(
        {"review_decision": "pending"}, approved_receipt=True,
    )
    assert is_locationless_bulk_candidate(
        {"review_decision": "selected"}, approved_receipt=False,
    )
    assert not is_locationless_bulk_candidate(
        {"review_decision": "pending"}, approved_receipt=False,
    )
    assert not is_locationless_bulk_candidate(
        {"review_decision": "ignored"}, approved_receipt=True,
    )


def test_locationless_bulk_ready_without_article_group_but_never_without_identity():
    assert classify_locationless_ready_line({
        "matched_household_article_id": "article-1",
        "matched_global_product_id": None,
        "selected_article_group_id": None,
        "target_location_id": "legacy-space",
    }) == (True, None, None)
    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": None,
        "matched_global_product_id": None,
        "selected_article_group_id": None,
        "target_location_id": "legacy-space",
    })
    assert ready is False
    assert stage == "article_resolution"
    assert "artikel" in reason.lower()


def test_processing_resolver_returns_real_null_location_for_none_policy(engine):
    with engine.begin() as conn:
        _seed_location_policy(conn)
        token = _processing_household_id.set("house-none")
        try:
            resolved = _policy_store_storage_target_location(
                None,
                lambda *_: {"legacy": True},
                conn,
                None,
            )
            assert resolved == {
                "location_id": None,
                "space_id": None,
                "sublocation_id": None,
                "location_label": "",
            }

            rejected = _policy_store_storage_target_location(
                None,
                lambda *_: {"legacy": True},
                conn,
                "legacy-space",
            )
            assert rejected is None
        finally:
            _processing_household_id.reset(token)


def test_processing_resolver_falls_back_to_legacy_without_batch_context(engine):
    with engine.begin() as conn:
        legacy_result = {"location_id": "legacy-space"}
        resolved = _policy_store_storage_target_location(
            None,
            lambda *_: legacy_result,
            conn,
            "legacy-space",
        )
        assert resolved is legacy_result


def test_installer_replaces_the_registered_process_route_and_resolver():
    original_endpoint = lambda batch_id, payload, authorization=None: {"legacy": True}
    original_resolver = lambda conn, target_location_id: {"legacy": target_location_id}
    route = SimpleNamespace(
        path="/api/purchase-import-batches/{batch_id}/process",
        methods={"POST"},
        endpoint=original_endpoint,
        dependant=SimpleNamespace(call=original_endpoint),
    )
    app = SimpleNamespace(state=SimpleNamespace(), routes=[route])
    main_module = SimpleNamespace(
        app=app,
        process_purchase_import_batch=original_endpoint,
        resolve_store_storage_target_location=original_resolver,
    )

    install_purchase_import_location_policy_patch(main_module)

    assert main_module.process_purchase_import_batch is not original_endpoint
    assert main_module.resolve_store_storage_target_location is not original_resolver
    assert route.endpoint is main_module.process_purchase_import_batch
    assert route.dependant.call is main_module.process_purchase_import_batch
    assert app.state.purchase_import_location_policy_patch_installed is True


def test_recover_approved_receipt_link_only_when_source_article_is_verified():
    from unittest.mock import Mock

    conn = Mock()
    conn.execute.return_value.mappings.return_value.first.return_value = {
        "household_article_id": "article-1",
        "global_product_id": None,
    }
    line = {
        "id": "line-1",
        "external_line_ref": "receipt-line:source-line-1",
        "matched_household_article_id": None,
        "matched_global_product_id": None,
        "article_override_mode": "auto",
    }
    batch = {"id": "batch-1", "household_id": "house-1", "source_reference": "receipt:source-1"}
    result = recover_explicit_approved_receipt_article_link(
        conn, line=line, batch=batch, approved_receipt=True,
    )
    assert result["matched_household_article_id"] == "article-1"
    assert conn.execute.call_count == 2
    query, params = conn.execute.call_args_list[0].args
    sql = str(query)
    assert "ha.household_id = rt.household_id" in sql
    assert "rt.household_id = :household_id" in sql
    assert "rt.approved_at IS NOT NULL" in sql
    assert params["household_id"] == "house-1"


def test_unapproved_or_explicitly_cleared_receipt_link_is_not_recovered():
    from unittest.mock import Mock

    conn = Mock()
    batch = {"id": "batch-1", "household_id": "house-1", "source_reference": "receipt:source-1"}
    for approved, override in [(False, "auto"), (True, "cleared")]:
        line = {
            "id": "line-1", "external_line_ref": "receipt-line:source-line-1",
            "matched_household_article_id": None,
            "matched_global_product_id": None,
            "article_override_mode": override,
        }
        assert recover_explicit_approved_receipt_article_link(
            conn, line=line, batch=batch, approved_receipt=approved,
        ) == line
    conn.execute.assert_not_called()


def test_unlinked_source_is_not_guessed_or_persisted():
    from unittest.mock import Mock

    conn = Mock()
    conn.execute.return_value.mappings.return_value.first.return_value = {
        "household_article_id": None,
        "global_product_id": None,
    }
    line = {
        "id": "line-1", "external_line_ref": "receipt-line:source-line-1",
        "matched_household_article_id": None,
        "matched_global_product_id": None,
    }
    batch = {"id": "batch-1", "household_id": "house-1", "source_reference": "receipt:source-1"}
    assert recover_explicit_approved_receipt_article_link(
        conn, line=line, batch=batch, approved_receipt=True,
    ) == line
    assert conn.execute.call_count == 1
