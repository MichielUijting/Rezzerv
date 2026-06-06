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

from __future__ import annotations

import io
import logging
import re
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    import ocrmypdf
except Exception:  # pragma: no cover
    ocrmypdf = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

LOGGER = logging.getLogger(__name__)
KNOWN_STORES = [
    'Albert Heijn', 'AH', 'Jumbo', 'Lidl', 'Plus', 'ALDI', 'Aldi', 'Action',
    'Gamma', 'Hornbach', 'Picnic', 'Bol', 'bol.com', 'Coolblue', 'Karwei', 'MediaMarkt',
]

def _html_to_text(value: str) -> str:
    if not value:
        return ''

    def _img_alt_replacement(match: re.Match[str]) -> str:
        tag = match.group(0)
        alt_match = re.search(r"(?i)\balt\s*=\s*['\"]([^'\"]+)['\"]", tag)
        if alt_match:
            return f"\n{alt_match.group(1)}\n"
        return '\n'

    normalized = str(value)
    normalized = re.sub(r'(?is)<img\b[^>]*>', _img_alt_replacement, normalized)
    normalized = re.sub(r'(?is)<\s*br\s*/?\s*>', '\n', normalized)
    normalized = re.sub(r'(?is)</?\s*(?:p|div|tr|td|table|section|article|li|ul|ol|h[1-6])\b[^>]*>', '\n', normalized)
    normalized = re.sub(r'(?is)<[^>]+>', ' ', normalized)
    normalized = normalized.replace('&nbsp;', ' ').replace('&euro;', 'EUR')
    normalized = re.sub(r'[ \t\r\f\v]+', ' ', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    normalized = normalized.replace(' \n', '\n').replace('\n ', '\n')
    return normalized.strip()


def _extract_pdf_text(file_bytes: bytes) -> str:
    if PdfReader is None:
        return ''
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        chunks: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ''
            if text:
                chunks.append(text)
        return '\n'.join(chunks)
    except Exception:
        return ''


def _preprocess_pdf_text(text: str) -> str:
    normalized = text or ''
    for store in KNOWN_STORES:
        normalized = re.sub(rf'({re.escape(store)})(?=\d)', r'\1\n', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'(\d{2}[/-]\d{2}[/-]\d{4}\s+\d{2}:\d{2}(?::\d{2})?)(?=[A-Z])', r'\1\n', normalized)
    normalized = re.sub(r'(?i)(TOTAAL|TE BETALEN|TOTAL)(?=\s*[-\d])', r'\n\1', normalized)
    normalized = re.sub(r'(\d{1,4}[\.,]\d{2})(?=[A-Z])', r'\1\n', normalized)
    return normalized


def _normalize_text_lines(text: str) -> list[str]:
    raw_lines = re.split(r'\r?\n+', text)
    lines: list[str] = []
    for line in raw_lines:
        normalized = re.sub(r'\s+', ' ', line).strip()
        if normalized:
            lines.append(normalized)
    return lines


def _ocr_pdf_text_with_ocrmypdf(file_bytes: bytes, filename: str) -> str:
    if ocrmypdf is None:
        return ''
    suffix = Path(filename).suffix.lower() or '.pdf'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-ocrpdf-') as temp_dir:
            temp_root = Path(temp_dir)
            input_path = temp_root / f'input{suffix}'
            output_path = temp_root / 'output.pdf'
            sidecar_path = temp_root / 'output.txt'
            input_path.write_bytes(file_bytes)
            ocrmypdf.ocr(
                input_path,
                output_path,
                language=['nld', 'eng'],
                sidecar=sidecar_path,
                force_ocr=True,
                deskew=True,
                rotate_pages=True,
                output_type='pdf',
                progress_bar=False,
            )
            sidecar_text = sidecar_path.read_text(encoding='utf-8', errors='ignore') if sidecar_path.exists() else ''
            if sidecar_text.strip():
                return sidecar_text
            if output_path.exists():
                return _extract_pdf_text(output_path.read_bytes())
    except Exception as exc:  # pragma: no cover - depends on optional OCR runtime
        LOGGER.warning('OCRmyPDF fallback mislukt voor %s: %s', filename, exc)
    return ''


def _normalize_store_specific_text(text: str) -> str:
    normalized = str(text or '').replace('\u00a0', ' ').replace('/uni00A0', ' ').replace('/uni00A01', ' 1 ')
    normalized = normalized.replace('/uni00A02', ' 2 ').replace('/uni00A03', ' 3 ').replace('/uni00A04', ' 4 ')
    normalized = normalized.replace('Â·', ' Â· ')
    normalized = re.sub(r'\s+â‚¬\s*', ' â‚¬ ', normalized)
    normalized = re.sub(r'[ 	]+', ' ', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized.strip()


def _extract_text_from_eml(file_bytes: bytes) -> tuple[str, str]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(file_bytes)
    except Exception:
        return '', ''
    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type not in {'text/plain', 'text/html'}:
            continue
        try:
            payload = part.get_content()
        except Exception:
            try:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or 'utf-8'
                payload = payload.decode(charset, errors='ignore') if isinstance(payload, (bytes, bytearray)) else str(payload)
            except Exception:
                payload = ''
        if content_type == 'text/plain' and payload:
            text_parts.append(str(payload))
        elif content_type == 'text/html' and payload:
            html_parts.append(str(payload))
    subject = str(message.get('subject') or '').strip()
    date_header = str(message.get('date') or '').strip()
    if subject:
        text_parts.insert(0, subject)
    if date_header:
        text_parts.insert(1 if subject else 0, date_header)
    plain_text = '\n'.join(text_parts).strip()
    html_text = ''
    if html_parts:
        html_source = '\n'.join(html_parts)
        if BeautifulSoup is not None:
            try:
                html_text = BeautifulSoup(html_source, 'html.parser').get_text('\n')
            except Exception:
                html_text = _html_to_text(html_source)
        else:
            html_text = _html_to_text(html_source)
    return _normalize_store_specific_text(plain_text), _normalize_store_specific_text(html_text)


def _convert_webp_to_png_bytes(file_bytes: bytes) -> bytes:
    if Image is None:
        return file_bytes
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except Exception:
        return file_bytes
