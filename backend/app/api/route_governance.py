from __future__ import annotations

CLASS_PROD = 'PROD'
CLASS_ADMIN = 'ADMIN'
CLASS_TEST = 'TEST'
CLASS_DEV_ONLY = 'DEV_ONLY'
CLASS_LEGACY = 'LEGACY'
CLASS_UNKNOWN = 'UNKNOWN'

RISK_LOW = 'LOW'
RISK_MEDIUM = 'MEDIUM'
RISK_HIGH = 'HIGH'


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
        routes.append(entry)
        counts[metadata['classification']] = counts.get(metadata['classification'], 0) + 1
        if metadata['risk'] == RISK_HIGH:
            high_risk.append(entry)
    routes.sort(key=lambda item: (item['classification'], item['route']))
    return {
        'manifest_name': 'R8-02A route governance manifest',
        'mode': 'read_only_inventory',
        'route_count': len(routes),
        'classification_counts': dict(sorted(counts.items())),
        'high_risk_count': len(high_risk),
        'high_risk_routes': sorted(high_risk, key=lambda item: item['route']),
        'routes': routes,
        'guardrails': {
            'routes_removed': False,
            'runtime_behavior_changed': False,
            'database_changed': False,
            'parser_or_ocr_changed': False,
        },
    }
