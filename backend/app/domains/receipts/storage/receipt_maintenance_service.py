"""Receipt maintenance facade.

Release 0 keeps behavior unchanged by delegating to the legacy service.
"""

from ....services.receipt_service import (  # noqa: F401
    repair_receipts_for_household,
    reparse_receipt,
)
