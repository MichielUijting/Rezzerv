from __future__ import annotations

"""Deprecated loyalty-line patch module.

R9-36N4:
This module is kept importable for compatibility only. Loyalty or savings-action
line behavior must live in the normal receipt parser flow, not in a patch module.
"""

from typing import Any


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    """Compatibility no-op."""
    return False
