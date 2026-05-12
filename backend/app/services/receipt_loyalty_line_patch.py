from __future__ import annotations

from typing import Any


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    """Release A safety rollback.

    The previous loyalty-line implementation was unstable in the current patch
    chain. Keep the module importable, but do not monkeypatch parser behavior.
    Receipt status remains governed by receipt_status_baseline_service_v4.py.
    """
    return True


install_receipt_loyalty_line_patch()
