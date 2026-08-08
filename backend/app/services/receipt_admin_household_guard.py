from __future__ import annotations

"""Compatibility shim for the former receipt-specific admin guard.

New code must import :mod:`app.services.platform_admin_route_guard` directly.
"""

from app.services.platform_admin_route_guard import (
    PROTECTED_MUTATIONS,
    authorize_platform_admin_request,
    deduplicate_receipt_parser_diagnosis_routes,
    install_platform_admin_route_guard,
)

_PROTECTED_REQUESTS = PROTECTED_MUTATIONS


def authorize_receipt_admin_request(method, path, authorization, require_platform_admin_user):
    return authorize_platform_admin_request(
        method,
        path,
        authorization,
        require_platform_admin_user,
    )


def install_receipt_admin_household_guard(main_module) -> None:
    install_platform_admin_route_guard(main_module)


__all__ = [
    "PROTECTED_MUTATIONS",
    "_PROTECTED_REQUESTS",
    "authorize_platform_admin_request",
    "authorize_receipt_admin_request",
    "deduplicate_receipt_parser_diagnosis_routes",
    "install_platform_admin_route_guard",
    "install_receipt_admin_household_guard",
]
