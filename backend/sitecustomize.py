from __future__ import annotations

try:
    from app.services import receipt_route_trace_patch  # noqa: F401
except Exception:
    # Startup tracing must never block the application. Detailed failures are
    # intentionally swallowed here because logging may not be configured yet.
    pass
