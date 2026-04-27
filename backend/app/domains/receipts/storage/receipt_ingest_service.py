"""Receipt ingest logic façade.

Release 0 delegates to the legacy service.
"""

from ....services.receipt_service import (  # noqa: F401
    ingest_receipt,
    ensure_default_receipt_sources,
)
