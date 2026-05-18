from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

FILTER_OLD = """        seen.add(key)
        filtered.append(line)
    return filtered
"""

FILTER_NEW = """        seen.add(key)
        # 8K-G: preserve diagnostic/runtime-only fields such as producer_trace.
        # Keep a shallow copy so later mutations cannot strip trace metadata from the original append path.
        filtered.append(dict(line))
    return filtered
"""

JUMBO_OLD = """            'confidence_score': 0.8,
            'source_index': 0,
        }]
"""

JUMBO_NEW = """            'confidence_score': 0.8,
            'source_index': 0,
            'producer_trace': {
                'filename': filename,
                'store_name': store_name,
                'function_name': '_parse_result_from_text_lines',
                'append_branch': 'jumbo_foto_3_manual_fallback',
                'parser_path': '_parse_result_from_text_lines.jumbo_foto_3_manual_fallback',
                'source_index': 0,
                'raw_line': None,
                'normalized_line': 'Jumbo stroopwafels',
                'label': 'Jumbo stroopwafels',
                'amount': 0.0,
                'classification': _classify_receipt_text_line('Jumbo stroopwafels', store_name=store_name, filename=filename),
                'classification_allows_append': True,
                'append_allowed': True,
                'caller_line_hint': 'manual Jumbo foto 3 fallback line rebuild',
            },
        }]
"""


def normalize(content: str) -> tuple[str, str]:
    newline = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), newline


def restore(content: str, newline: str) -> str:
    return content.replace('\n', newline) if newline != '\n' else content


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        return content
    count = content.count(old)
    if count != 1:
        raise SystemExit(f'Patchblok niet exact 1x gevonden: {label} ({count}x)')
    return content.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')
    raw = TARGET.read_text(encoding='utf-8')
    content, newline = normalize(raw)
    updated = content
    updated = replace_once(updated, FILTER_OLD, FILTER_NEW, 'preserve producer_trace in _filter_non_product_receipt_lines')
    updated = replace_once(updated, JUMBO_OLD, JUMBO_NEW, 'preserve producer_trace in Jumbo foto 3 fallback rebuild')
    if updated == content:
        print('8K-G producer_trace preservation was al aanwezig')
        return
    TARGET.write_text(restore(updated, newline), encoding='utf-8', newline='')
    print('8K-G producer_trace preservation toegepast op receipt_service.py')


if __name__ == '__main__':
    main()
