"""Store, branch, purchase-date and total extraction for receipts.

Compatibility façade: delegates to the legacy receipt service during Release 0.
"""

from ....services.receipt_service import (  # noqa: F401
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
    _looks_like_store_branch_line,
    _purchase_at_from_lines,
    _store_branch_from_lines,
    _store_from_text,
    _total_amount_from_lines,
)
