"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import inspect
import os
from functools import wraps

from fastapi import HTTPException
from fastapi.applications import FastAPI

CLASS_PROD = 'PROD'
CLASS_ADMIN = 'ADMIN'
CLASS_TEST = 'TEST'
CLASS_DEV_ONLY = 'DEV_ONLY'
CLASS_LEGACY = 'LEGACY'
CLASS_UNKNOWN = 'UNKNOWN'

RISK_LOW = 'LOW'
RISK_MEDIUM = 'MEDIUM'
RISK_HIGH = 'HIGH'
DEV_TOOLS_ENV_VAR = 'REZZERV_DEV_TOOLS_ENABLED'
_DEV_ROUTE_GUARD_PATCHED = False
_ORIGINAL_FASTAPI_ADD_API_ROUTE = FastAPI.add_api_route


def _route(*parts: str) -> str:
    return ''.join(parts)


HIGH_RISK_EXACT_ROUTES = {
    _route('/api/dev/', 'reset', '-data'),
    _route('/api/dev/', 'generate', '-demo-data'),
    _route('/api/dev/', 'generate', '-large-dataset'),
    _route('/api/dev/regression/', 'reset'),
    _route('/api/dev/regression/', 'cleanup'),
    _route('/api/dev/receipts/', 'purge-deleted'),
}

CLASSIFICATION_PREFIXES = (
    ('/api/health', CLASS_PROD, RISK_LOW),
    ('/api/version', CLASS_PROD, RISK_LOW),
    ('/api/admin/', CLASS_ADMIN, RISK_MEDIUM),
    ('/api/testing/', CLASS_TEST, RISK_LOW),
    ('/api/dev/', CLASS_DEV_ONLY, RISK_MEDIUM),
    ('/api/articles/household-details', CLASS_LEGACY, RISK_MEDIUM),
    ('/api/articles/', CLASS_LEGACY, RISK_MEDIUM),
    ('/api/', CLASS_PROD, RISK_MEDIUM),
)


def dev_tools_enabled() -> bool:
    value = str(os.getenv(DEV_TOOLS_ENV_VAR, '') or '').strip().lower()
    return value in {'1', 'true', 'yes', 'on'}


def require_dev_tools_enabled(path: str) -> None:
    if dev_tools_enabled():
        return
    raise HTTPException(
        status_code=403,
        detail={
            'status': 'blocked',
            'reason': 'dev tools disabled',
            'route': path,
            'required_env': f'{DEV_TOOLS_ENV_VAR}=true',
        },
    )


def _guard_high_risk_endpoint(path: str, endpoint):
    if path not in HIGH_RISK_EXACT_ROUTES:
        return endpoint
    if inspect.iscoroutinefunction(endpoint):
        @wraps(endpoint)
        async def async_guarded_endpoint(*args, **kwargs):
            require_dev_tools_enabled(path)
            return await endpoint(*args, **kwargs)
        return async_guarded_endpoint

    @wraps(endpoint)
    def guarded_endpoint(*args, **kwargs):
        require_dev_tools_enabled(path)
        return endpoint(*args, **kwargs)
    return guarded_endpoint


def install_high_risk_dev_route_guard() -> None:
    global _DEV_ROUTE_GUARD_PATCHED
    if _DEV_ROUTE_GUARD_PATCHED:
        return

    def guarded_add_api_route(self, path, endpoint, *args, **kwargs):
        endpoint = _guard_high_risk_endpoint(str(path), endpoint)
        return _ORIGINAL_FASTAPI_ADD_API_ROUTE(self, path, endpoint, *args, **kwargs)

    FastAPI.add_api_route = guarded_add_api_route
    _DEV_ROUTE_GUARD_PATCHED = True


install_high_risk_dev_route_guard()


def classify_route(path: str) -> dict:
    classification = CLASS_UNKNOWN
    risk = RISK_LOW
    for prefix, route_class, route_risk in CLASSIFICATION_PREFIXES:
        if path == prefix.rstrip('/') or path.startswith(prefix):
            classification = route_class
            risk = route_risk
            break
    if path in HIGH_RISK_EXACT_ROUTES:
        risk = RISK_HIGH
        classification = CLASS_DEV_ONLY
    po_visible = classification == CLASS_PROD and risk != RISK_HIGH
    return {
        'classification': classification,
        'risk': risk,
        'po_visible': po_visible,
        'action': 'review_governance_before_cleanup' if classification != CLASS_PROD or risk == RISK_HIGH else 'keep_in_default_runtime',
    }


def build_route_governance_manifest(app) -> dict:
    routes = []
    counts = {}
    high_risk = []
    for route in app.routes:
        path = getattr(route, 'path', '')
        if not path.startswith('/api/'):
            continue
        methods = sorted(getattr(route, 'methods', []) or [])
        metadata = classify_route(path)
        entry = {
            'route': path,
            'methods': methods,
            'name': getattr(route, 'name', None),
            **metadata,
        }
        if metadata['risk'] == RISK_HIGH:
            entry['guard'] = {
                'enabled': True,
                'default_allows_execution': dev_tools_enabled(),
                'required_env': f'{DEV_TOOLS_ENV_VAR}=true',
            }
        routes.append(entry)
        counts[metadata['classification']] = counts.get(metadata['classification'], 0) + 1
        if metadata['risk'] == RISK_HIGH:
            high_risk.append(entry)
    routes.sort(key=lambda item: (item['classification'], item['route']))
    return {
        'manifest_name': 'R8-02B route governance manifest',
        'mode': 'read_only_inventory_with_high_risk_guard',
        'dev_tools_enabled': dev_tools_enabled(),
        'dev_tools_env_var': DEV_TOOLS_ENV_VAR,
        'route_count': len(routes),
        'classification_counts': dict(sorted(counts.items())),
        'high_risk_count': len(high_risk),
        'high_risk_routes': sorted(high_risk, key=lambda item: item['route']),
        'routes': routes,
        'guardrails': {
            'routes_removed': False,
            'database_changed': False,
            'parser_or_ocr_changed': False,
            'high_risk_dev_routes_blocked_by_default': not dev_tools_enabled(),
        },
    }
