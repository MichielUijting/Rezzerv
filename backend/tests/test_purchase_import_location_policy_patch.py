from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
)
from app.services.purchase_import_location_policy_patch import (
    _policy_store_storage_target_location,
    _processing_household_id,
    classify_locationless_ready_line,
    install_purchase_import_location_policy_patch,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _seed_location_policy(conn):
    conn.execute(text("""
        CREATE TABLE spaces (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            household_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))
    conn.execute(text("""
        CREATE TABLE sublocations (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            space_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))
    ensure_household_product_configuration_foundation(conn)
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
        VALUES ('legacy-space', 'Oude ruimte', 'house-none', 1)
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
    assert ready is False
    assert reason == "Nog geen artikelgroep gekozen"
    assert stage == "article_group_resolution"


def test_locationless_ready_only_rejects_a_stored_location_instead_of_normalizing_it():
    ready, reason, stage = classify_locationless_ready_line({
        "matched_household_article_id": "article-1",
        "matched_global_product_id": None,
        "selected_article_group_id": "group-1",
        "target_location_id": "legacy-space",
    })
    assert ready is False
    assert "zonder locatie" in str(reason)
    assert stage == "purchase_event_write"


def test_processing_resolver_returns_real_null_location_for_none_policy():
    engine = _engine()
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


def test_processing_resolver_falls_back_to_legacy_without_batch_context():
    engine = _engine()
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
