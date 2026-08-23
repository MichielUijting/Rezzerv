from __future__ import annotations


PURCHASE_IMPORT_BATCH_DIAGNOSTICS_PERMISSION = "platform.diagnostics.view"
PURCHASE_IMPORT_BATCH_DIAGNOSTICS_ROUTE_PREFIX = (
    "/api/testing/diagnostics/purchase-import-batches/"
)


def required_purchase_import_batch_diagnostics_permission(
    method: str,
    path: str,
) -> str | None:
    if str(method or "").upper() != "GET":
        return None

    normalized_path = str(path or "")
    if not normalized_path.startswith(PURCHASE_IMPORT_BATCH_DIAGNOSTICS_ROUTE_PREFIX):
        return None

    batch_id = normalized_path[len(PURCHASE_IMPORT_BATCH_DIAGNOSTICS_ROUTE_PREFIX):]
    if not batch_id or "/" in batch_id:
        return None
    return PURCHASE_IMPORT_BATCH_DIAGNOSTICS_PERMISSION
