"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

"""Albert Heijn diagnostics profile.

Diagnostics may only observe and report; they must not change parser output.
"""

from __future__ import annotations

from typing import Any


def build_ah_total_diagnostics(result: Any) -> dict[str, Any]:
    """Build serializable diagnostics for the AH total mini frame."""
    selected = getattr(result, 'selected', None) or None
    return {
        'profile': 'ah',
        'component': 'totals',
        'selected_amount': str(getattr(result, 'amount', None)) if getattr(result, 'amount', None) is not None else None,
        'selected_anchor': selected.get('anchor') if isinstance(selected, dict) else None,
        'selected': selected,
        'explicit_total_found': bool(getattr(result, 'explicit_total_found', False)),
        'candidates': list(getattr(result, 'candidates', []) or []),
        'rejected': list(getattr(result, 'rejected', []) or []),
    }
