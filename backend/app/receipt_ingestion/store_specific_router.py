from __future__ import annotations

from collections.abc import Callable
from email import policy
from email.parser import BytesParser
from typing import Any

ParserResult = Any
NormalizeText = Callable[[str], str]
HtmlToText = Callable[[str], str]
PdfParser = Callable[[str, str], ParserResult | None]
EmailParser = Callable[..., ParserResult | None]


def _has_useful_result(result: ParserResult | None) -> bool:
    return result is not None and bool(
        getattr(result, 'lines', None)
        or getattr(result, 'total_amount', None)
        or getattr(result, 'purchase_at', None)
        or getattr(result, 'store_name', None)
    )


def _email_header_date(file_bytes: bytes) -> str | None:
    try:
        message = BytesParser(policy=policy.default).parsebytes(file_bytes)
        return str(message.get('date') or '').strip()
    except Exception:
        return None


def route_store_specific_result(
    *,
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    direct_text: str = '',
    html_text: str = '',
    normalize_store_specific_text: NormalizeText,
    html_to_text: HtmlToText,
    pdf_parsers: tuple[PdfParser, ...],
    email_parsers: tuple[EmailParser, ...],
) -> ParserResult | None:
    """Route store-specific receipt parsing without owning parser behavior.

    R7b-4 intentionally moves only the routing order out of receipt_service.py.
    The parser callables are still supplied by receipt_service.py for now, so the
    implementation remains behaviour-preserving while creating a clear module
    boundary for later store-specific parser extraction.
    """
    lower_name = filename.lower()
    text = normalize_store_specific_text(direct_text)
    normalized_html = normalize_store_specific_text(html_to_text(html_text) if html_text else '')

    if lower_name.endswith('.pdf'):
        for parser in pdf_parsers:
            result = parser(text, filename)
            if _has_useful_result(result):
                return result

    header_date = None
    if lower_name.endswith('.eml') or mime_type == 'message/rfc822':
        header_date = _email_header_date(file_bytes)

    can_try_email_parsers = (
        lower_name.endswith('.eml')
        or mime_type == 'message/rfc822'
        or mime_type in {'text/html', 'text/plain'}
        or lower_name.endswith(('.html', '.htm', '.txt'))
    )
    if can_try_email_parsers:
        for parser in email_parsers:
            result = parser(text, normalized_html, filename, header_date=header_date)
            if _has_useful_result(result):
                return result

    return None
