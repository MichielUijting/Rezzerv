"""Server-side authorization policy for external-database routes."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import evaluate_platform_permission

EXTERNAL_DATABASE_PREFIX = "/api/external-databases"
EXTERNAL_PRODUCTS_OFF_SEARCH_PATH = "/api/external-products/off/search"

_EXTERNAL_DATABASE_SEARCH_SUFFIXES = (
    "/match-preview",
    "/diagnose-real-candidates",
    "/off/search-preview",
    "/coverage/receipt-items",
)


def required_external_database_permission(method: str, path: str) -> str | None:
    normalized_method = str(method or "").strip().upper()
    normalized_path = str(path or "").strip()
    covered = (
        normalized_path == EXTERNAL_DATABASE_PREFIX
        or normalized_path.startswith(EXTERNAL_DATABASE_PREFIX + "/")
        or normalized_path == EXTERNAL_PRODUCTS_OFF_SEARCH_PATH
    )
    if not covered or normalized_method == "OPTIONS":
        return None

    if normalized_method in {"GET", "HEAD"}:
        return "platform.external_products.view"
    if normalized_path == EXTERNAL_PRODUCTS_OFF_SEARCH_PATH:
        return "platform.external_products.search"
    if any(normalized_path.endswith(suffix) for suffix in _EXTERNAL_DATABASE_SEARCH_SUFFIXES):
        return "platform.external_products.search"
    return "platform.external_products.link_existing"


def authorize_external_database_request(
    conn: Connection,
    *,
    user_id: str,
    method: str,
    path: str,
) -> str | None:
    permission_key = required_external_database_permission(method, path)
    if permission_key is None:
        return None
    decision = evaluate_platform_permission(
        conn,
        user_id=str(user_id),
        permission_key=permission_key,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail="Onvoldoende platformbevoegdheid voor externe databases",
        )
    return permission_key
