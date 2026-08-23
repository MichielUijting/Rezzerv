from __future__ import annotations


EXTERNAL_RELATION_BATCH_DECISION_PERMISSION = "platform.external_products.link_existing"
EXTERNAL_RELATION_BATCH_DECISION_ROUTES = frozenset(
    {
        ("POST", "/api/admin/external-relations/batch/decision"),
    }
)


def required_external_relation_batch_decision_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in EXTERNAL_RELATION_BATCH_DECISION_ROUTES:
        return None
    return EXTERNAL_RELATION_BATCH_DECISION_PERMISSION
