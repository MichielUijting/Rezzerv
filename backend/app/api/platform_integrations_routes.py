from __future__ import annotations

from fastapi import APIRouter

from app.integrations.receipt_scanners import runtime as receipt_scanner_runtime
from app.integrations.receipt_scanners.errors import ProviderConfigurationError
from app.services import email_config_service
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_INTEGRATIONS_MANAGE_PERMISSION = "platform.integrations.manage"

router = APIRouter()


def _receipt_scanner_status() -> dict:
    try:
        gateway = receipt_scanner_runtime.get_receipt_scanner_gateway()
    except ProviderConfigurationError:
        return {
            "key": "receipt-scanner",
            "label": "Kassabonscanner",
            "scope": "platform",
            "provider": None,
            "status": "configuration_error",
            "contract_version": receipt_scanner_runtime.CONTRACT_VERSION,
            "available_providers": [receipt_scanner_runtime.DEFAULT_PROVIDER],
        }

    return {
        "key": "receipt-scanner",
        "label": "Kassabonscanner",
        "scope": "platform",
        "provider": gateway.registry.active_provider_code,
        "status": "ready",
        "contract_version": receipt_scanner_runtime.CONTRACT_VERSION,
        "available_providers": list(gateway.registry.available_provider_codes()),
    }


def _outbound_email_status() -> dict:
    delivery_enabled = email_config_service.outbound_email_delivery_enabled()
    api_key_configured = email_config_service.resend_api_key_ready()
    sender_configured, _sender_reason = email_config_service.outbound_email_sender_ready()

    if not delivery_enabled:
        status = "disabled"
    elif api_key_configured and sender_configured:
        status = "ready"
    else:
        status = "incomplete"

    return {
        "key": "outbound-email",
        "label": "Uitgaande e-mail",
        "scope": "platform",
        "provider": "resend",
        "status": status,
        "delivery_enabled": bool(delivery_enabled),
        "api_key_configured": bool(api_key_configured),
        "sender_configured": bool(sender_configured),
    }


@router.get("/api/platform/integrations")
def get_platform_integrations() -> dict:
    """Return a curated, secret-free view of platform-wide integrations only."""

    require_platform_permission_from_session(PLATFORM_INTEGRATIONS_MANAGE_PERMISSION)
    items = [
        _receipt_scanner_status(),
        _outbound_email_status(),
    ]
    return {
        "items": items,
        "count": len(items),
        "read_only": True,
        "household_context_used": False,
    }
