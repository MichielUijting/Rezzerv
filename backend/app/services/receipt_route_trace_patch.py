from __future__ import annotations

import logging
import time
from typing import Any, Callable

from fastapi.routing import APIRoute

LOGGER = logging.getLogger(__name__)
_TARGET_PATHS = {'/api/receipts/import', '/api/receipts/share-target', '/api/receipts/email-import'}
_ORIGINAL_GET_ROUTE_HANDLER = APIRoute.get_route_handler
_INSTALLED = False


def _route_path(route: Any) -> str:
    return str(getattr(route, 'path', '') or '')


def _route_name(route: Any) -> str:
    endpoint = getattr(route, 'endpoint', None)
    if endpoint is not None:
        return str(getattr(endpoint, '__name__', '') or '')
    return ''


def _methods(route: Any) -> str:
    methods = getattr(route, 'methods', None) or []
    return ','.join(sorted(str(method) for method in methods))


def _wrapped_get_route_handler(self: APIRoute) -> Callable[..., Any]:
    original_handler = _ORIGINAL_GET_ROUTE_HANDLER(self)
    path = _route_path(self)
    if path not in _TARGET_PATHS:
        return original_handler
    route_name = _route_name(self)
    route_methods = _methods(self)

    async def traced_route_handler(request):
        start = time.perf_counter()
        content_type = request.headers.get('content-type')
        content_length = request.headers.get('content-length')
        LOGGER.info(
            'receipt_upload_route_entered path=%s methods=%s function=%s content_type=%s content_length=%s',
            path,
            route_methods,
            route_name,
            content_type,
            content_length,
        )
        try:
            response = await original_handler(request)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.info(
                'receipt_upload_route_finished path=%s function=%s status_code=%s elapsed_ms=%s',
                path,
                route_name,
                getattr(response, 'status_code', None),
                elapsed_ms,
            )
            return response
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception(
                'receipt_upload_route_failed path=%s function=%s elapsed_ms=%s error=%s',
                path,
                route_name,
                elapsed_ms,
                exc,
            )
            raise

    return traced_route_handler


def install_receipt_route_trace_patch() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    APIRoute.get_route_handler = _wrapped_get_route_handler
    _INSTALLED = True
    LOGGER.info('Receipt upload route trace patch installed')
    return True


install_receipt_route_trace_patch()
