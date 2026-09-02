"""Runtime contract for JSON-safe receipt import batches.

PostgreSQL returns native Python values such as ``datetime`` and ``Decimal``
for typed columns where the historical SQLite runtime commonly returned
string/number-like values. Receipt ZIP batches persist their incremental result
list as JSON, so these values must be normalized at the batch boundary.

The contract also guards the background worker so an unexpected exception can
never leave a batch permanently marked as ``running``. The ZIP runtime uses
the extracted receipt-source helper for EML members, so its dependencies are
configured from the actual application entrypoint at the same boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps
from typing import Any

from app.services.receipt_source_helper_service import (
    configure_receipt_source_helper_service,
)


def json_safe_receipt_import_value(value: Any) -> Any:
    """Recursively normalize database-native values for receipt batch JSON."""

    if isinstance(value, Mapping):
        return {
            str(key): json_safe_receipt_import_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_safe_receipt_import_value(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_receipt_source_household_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("household_id is verplicht")
    return normalized


def _serialize_receipt_source_row(row: Any) -> dict[str, Any]:
    data = dict(row or {})
    if "is_active" in data:
        data["is_active"] = bool(data.get("is_active"))
    for key in ("last_scan_at", "created_at", "updated_at"):
        current = data.get(key)
        if isinstance(current, (datetime, date, time)):
            data[key] = current.isoformat()
    return data


def _configure_receipt_source_helper_runtime(legacy_main: Any) -> None:
    engine = getattr(legacy_main, "engine", None)
    text = getattr(legacy_main, "text", None)
    if engine is None or text is None:
        return

    normalize_household_id = getattr(legacy_main, "normalize_household_id", None)
    if not callable(normalize_household_id):
        normalize_household_id = _normalize_receipt_source_household_id

    serialize_receipt_source = getattr(legacy_main, "serialize_receipt_source", None)
    if not callable(serialize_receipt_source):
        serialize_receipt_source = _serialize_receipt_source_row

    configure_receipt_source_helper_service(
        engine=engine,
        text=text,
        normalize_household_id=normalize_household_id,
        serialize_receipt_source=serialize_receipt_source,
    )


def install_receipt_import_batch_runtime_contract(legacy_main: Any) -> None:
    """Install receipt batch JSON, source-helper and worker runtime contracts."""

    _configure_receipt_source_helper_runtime(legacy_main)

    importer = legacy_main.import_uploaded_receipt_payload
    if not getattr(importer, "_rezzerv_receipt_batch_json_safe", False):
        @wraps(importer)
        def json_safe_importer(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = importer(*args, **kwargs)
            return json_safe_receipt_import_value(result)

        json_safe_importer._rezzerv_receipt_batch_json_safe = True
        legacy_main.import_uploaded_receipt_payload = json_safe_importer

    worker = legacy_main._run_receipt_zip_import_batch
    if not getattr(worker, "_rezzerv_receipt_batch_guarded", False):
        @wraps(worker)
        def guarded_worker(batch_id: str, *args: Any, **kwargs: Any) -> Any:
            try:
                return worker(batch_id, *args, **kwargs)
            except Exception as exc:
                legacy_main.logger.exception(
                    "Zip-import batch %s onverwacht gestopt",
                    batch_id,
                )
                try:
                    # Preserve the last successfully persisted counts/results.
                    # Only make the batch terminal and expose the worker error.
                    legacy_main.update_receipt_import_batch(
                        batch_id,
                        status="failed",
                        error_message=str(exc),
                        finished_at=datetime.utcnow().isoformat(),
                    )
                except Exception:
                    legacy_main.logger.exception(
                        "Zip-import batch %s kon niet als failed worden vastgelegd",
                        batch_id,
                    )
                return None

        guarded_worker._rezzerv_receipt_batch_guarded = True
        legacy_main._run_receipt_zip_import_batch = guarded_worker
