import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services import receipt_source_helper_service
from app.services.receipt_import_batch_runtime_contract import (
    install_receipt_import_batch_runtime_contract,
    json_safe_receipt_import_value,
)


def test_postgresql_native_duplicate_values_are_json_safe():
    purchase_at = datetime(2026, 3, 20, 16, 27, tzinfo=timezone.utc)
    value = {
        "duplicate": True,
        "existing_receipt": {
            "purchase_at": purchase_at,
            "total_amount": Decimal("42.50"),
        },
    }

    normalized = json_safe_receipt_import_value(value)

    assert normalized["existing_receipt"]["purchase_at"] == purchase_at.isoformat()
    assert normalized["existing_receipt"]["total_amount"] == 42.5
    assert json.loads(json.dumps(normalized))["duplicate"] is True


def test_installed_importer_normalizes_nested_postgresql_values():
    purchase_at = datetime(2026, 3, 20, 16, 27, tzinfo=timezone.utc)

    def importer(*args, **kwargs):
        return {
            "duplicate": True,
            "existing_receipt": {
                "purchase_at": purchase_at,
                "total_amount": Decimal("12.34"),
            },
        }

    fake_main = SimpleNamespace(
        import_uploaded_receipt_payload=importer,
        _run_receipt_zip_import_batch=lambda *args, **kwargs: None,
        update_receipt_import_batch=lambda *args, **kwargs: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
    )

    install_receipt_import_batch_runtime_contract(fake_main)
    result = fake_main.import_uploaded_receipt_payload()

    assert result["existing_receipt"]["purchase_at"] == purchase_at.isoformat()
    assert result["existing_receipt"]["total_amount"] == 12.34
    json.dumps(result)


def test_receipt_source_helper_is_configured_for_eml_batch_runtime():
    fake_engine = object()
    fake_text = lambda value: value
    fake_main = SimpleNamespace(
        engine=fake_engine,
        text=fake_text,
        import_uploaded_receipt_payload=lambda *args, **kwargs: {},
        _run_receipt_zip_import_batch=lambda *args, **kwargs: None,
        update_receipt_import_batch=lambda *args, **kwargs: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
    )

    install_receipt_import_batch_runtime_contract(fake_main)

    engine, text, normalize_household_id, serialize_receipt_source = (
        receipt_source_helper_service._require_configured()
    )
    assert engine is fake_engine
    assert text is fake_text
    assert normalize_household_id(" 1 ") == "1"

    created_at = datetime(2026, 9, 2, 20, 17, tzinfo=timezone.utc)
    serialized = serialize_receipt_source(
        {
            "id": "1-email-route",
            "household_id": "1",
            "type": "email",
            "label": "E-mail",
            "source_path": "bon+1@example.test",
            "is_active": 1,
            "created_at": created_at,
        }
    )
    assert serialized["id"] == "1-email-route"
    assert serialized["is_active"] is True
    assert serialized["created_at"] == created_at.isoformat()


def test_unexpected_worker_exception_marks_batch_failed():
    updates = []
    log_calls = []

    def failing_worker(*args, **kwargs):
        raise TypeError("Object of type datetime is not JSON serializable")

    def update_batch(batch_id, **values):
        updates.append((batch_id, values))

    fake_main = SimpleNamespace(
        import_uploaded_receipt_payload=lambda *args, **kwargs: {},
        _run_receipt_zip_import_batch=failing_worker,
        update_receipt_import_batch=update_batch,
        logger=SimpleNamespace(
            exception=lambda *args, **kwargs: log_calls.append((args, kwargs))
        ),
    )

    install_receipt_import_batch_runtime_contract(fake_main)
    result = fake_main._run_receipt_zip_import_batch(
        "batch-1", "1", "source-1", "receipts.zip", []
    )

    assert result is None
    assert updates
    batch_id, values = updates[-1]
    assert batch_id == "batch-1"
    assert values["status"] == "failed"
    assert "datetime is not JSON serializable" in values["error_message"]
    assert values["finished_at"]
    assert log_calls


def test_runtime_contract_install_is_idempotent():
    fake_main = SimpleNamespace(
        import_uploaded_receipt_payload=lambda *args, **kwargs: {},
        _run_receipt_zip_import_batch=lambda *args, **kwargs: None,
        update_receipt_import_batch=lambda *args, **kwargs: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
    )

    install_receipt_import_batch_runtime_contract(fake_main)
    importer = fake_main.import_uploaded_receipt_payload
    worker = fake_main._run_receipt_zip_import_batch

    install_receipt_import_batch_runtime_contract(fake_main)

    assert fake_main.import_uploaded_receipt_payload is importer
    assert fake_main._run_receipt_zip_import_batch is worker
