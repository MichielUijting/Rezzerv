from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b7')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_anchor = "from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n"
router_import = "from app.receipt_ingestion.store_specific_router import route_store_specific_result\n"
if router_import not in content:
    if import_anchor not in content:
        raise SystemExit('R7b-7 aborted: parser_debug_serializer import anchor not found.')
    content = content.replace(import_anchor, import_anchor + router_import, 1)

old_function = '''def _parse_store_specific_result(file_bytes: bytes, filename: str, mime_type: str, direct_text: str = '', html_text: str = '') -> ReceiptParseResult | None:
    lower_name = filename.lower()
    text = _normalize_store_specific_text(direct_text)
    normalized_html = _normalize_store_specific_text(_html_to_text(html_text) if html_text else '')
    if lower_name.endswith('.pdf'):
        for parser in (_parse_action_pdf_result, _parse_gamma_pdf_result, _parse_hornbach_pdf_result, _parse_lidl_invoice_pdf_result):
            result = parser(text, filename)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result

    header_date = None
    if lower_name.endswith('.eml') or mime_type == 'message/rfc822':
        try:
            message = BytesParser(policy=policy.default).parsebytes(file_bytes)
            header_date = str(message.get('date') or '').strip()
        except Exception:
            header_date = None

    can_try_email_parsers = (
        lower_name.endswith('.eml')
        or mime_type == 'message/rfc822'
        or mime_type in {'text/html', 'text/plain'}
        or lower_name.endswith(('.html', '.htm', '.txt'))
    )
    if can_try_email_parsers:
        for parser in (_parse_bol_email_result, _parse_picnic_email_result):
            result = parser(text, normalized_html, filename, header_date=header_date)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result
    return None
'''

new_function = '''def _parse_store_specific_result(file_bytes: bytes, filename: str, mime_type: str, direct_text: str = '', html_text: str = '') -> ReceiptParseResult | None:
    return route_store_specific_result(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        direct_text=direct_text,
        html_text=html_text,
        normalize_store_specific_text=_normalize_store_specific_text,
        html_to_text=_html_to_text,
        pdf_parsers=(
            _parse_action_pdf_result,
            _parse_gamma_pdf_result,
            _parse_hornbach_pdf_result,
            _parse_lidl_invoice_pdf_result,
        ),
        email_parsers=(
            _parse_bol_email_result,
            _parse_picnic_email_result,
        ),
    )
'''

if new_function not in content:
    if old_function not in content:
        raise SystemExit('R7b-7 aborted: legacy _parse_store_specific_result function block not found.')
    content = content.replace(old_function, new_function, 1)

for forbidden in ["BytesParser(policy=policy.default).parsebytes(file_bytes)", "can_try_email_parsers = ("]:
    if forbidden in content:
        raise SystemExit(f'R7b-7 guard failed: {forbidden!r} still present in receipt_service.py router wrapper.')

TARGET.write_text(content, encoding='utf-8')
print('R7b-7 store-specific router wiring applied to', TARGET)
print('Backup written to', BACKUP)
