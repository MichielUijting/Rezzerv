from __future__ import annotations

from typing import Any

_LAST_INGEST_DEBUG_CAPTURE: dict[str, Any] = {}


def get_latest_ingest_debug_capture() -> dict[str, Any]:
    return dict(_LAST_INGEST_DEBUG_CAPTURE)


def install_parser_quality_patch(*_: Any) -> bool:
    return False
