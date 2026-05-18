from __future__ import annotations

from collections.abc import Callable
from typing import Any

ParseTextLines = Callable[..., Any]


def route_generic_text_parser(
    *,
    parse_text_lines: ParseTextLines,
    text_lines: list[str],
    filename: str,
    rich_confidence: float,
    partial_confidence: float,
    review_confidence: float,
) -> Any:
    """Boundary for the generic OCR/text-line receipt parser.

    R7b-8 intentionally does not move or change parser behavior yet. It creates
    a receipt_ingestion module boundary so receipt_service.py can become an
    orchestrator while the existing parser implementation remains callable and
    behavior-preserving.
    """
    return parse_text_lines(
        text_lines,
        filename,
        rich_confidence=rich_confidence,
        partial_confidence=partial_confidence,
        review_confidence=review_confidence,
    )
