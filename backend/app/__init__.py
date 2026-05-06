"""Package initialisation for Rezzerv backend.

Route registration belongs in app.main, not in import-time background threads.
Runtime patches that must exist before app.main imports direct parser bindings may still be installed here.
"""

from __future__ import annotations

try:
    from .services.receipt_chain_duplicate_merge_patch import install_receipt_chain_duplicate_merge_patch
    install_receipt_chain_duplicate_merge_patch()
except Exception:
    pass
