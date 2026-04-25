"""Rezzerv application package bootstrap.

Keep this file lightweight. It activates domain-level compatibility wrappers before
app.main imports service symbols directly from app.services.*.
"""

# Activate receipt domain monkey patches early for legacy service imports.
try:
    import app.domains.receipts.receipt_service  # noqa: F401
except Exception:
    # Startup must not fail because an optional receipt-domain dependency is absent.
    pass
