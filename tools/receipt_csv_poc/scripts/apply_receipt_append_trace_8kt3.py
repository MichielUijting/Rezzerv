from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')


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
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    return content.replace(old, new, 1)


CANONICAL_OLD = """                'confidence_score': 0.85,\n                'source_index': source_index,\n            }\n        )\n"""

CANONICAL_NEW = """                'confidence_score': 0.85,\n                'source_index': source_index,\n                'producer_trace': {\n                    'filename': filename,\n                    'store_name': store_name,\n                    'function_name': '_extract_receipt_lines',\n                    'append_branch': 'append_line',\n                    'parser_path': '_extract_receipt_lines.append_line',\n                    'source_index': source_index,\n                    'raw_line': lines[source_index] if 0 <= source_index < len(lines) else None,\n                    'normalized_line': re.sub(r'\\s+', ' ', str(lines[source_index] if 0 <= source_index < len(lines) else '')).strip(),\n                    'label': label_value,\n                    'amount': _amount_to_float(line_total),\n                    'classification': _classify_receipt_text_line(label_value, store_name=store_name, filename=filename),\n                    'classification_allows_append': _classify_receipt_text_line(label_value, store_name=store_name, filename=filename) not in {'ignore', 'metadata', 'footer_payment_tax'},\n                    'append_allowed': True,\n                    'caller_line_hint': 'canonical append_line extracted.append',\n                },\n            }\n        )\n"""

SPARSE_QTY_OLD = """                    'confidence_score': 0.55,\n                    'source_index': source_index,\n                })\n"""

SPARSE_QTY_NEW = """                    'confidence_score': 0.55,\n                    'source_index': source_index,\n                    'producer_trace': {\n                        'filename': filename,\n                        'store_name': store_name,\n                        'function_name': '_extract_sparse_receipt_lines',\n                        'append_branch': 'qty_x_amount',\n                        'parser_path': '_extract_sparse_receipt_lines.qty_x_amount',\n                        'source_index': source_index,\n                        'raw_line': raw_line,\n                        'normalized_line': normalized,\n                        'label': label,\n                        'amount': _amount_to_float(amount),\n                        'classification': label_classification,\n                        'classification_allows_append': label_classification not in {'ignore', 'metadata', 'footer_payment_tax'},\n                        'append_allowed': True,\n                        'caller_line_hint': 'sparse qty_x_amount extracted.append',\n                    },\n                })\n"""

SPARSE_AMOUNT_OLD = """            'confidence_score': 0.5,\n            'source_index': source_index,\n        })\n"""

SPARSE_AMOUNT_NEW = """            'confidence_score': 0.5,\n            'source_index': source_index,\n            'producer_trace': {\n                'filename': filename,\n                'store_name': store_name,\n                'function_name': '_extract_sparse_receipt_lines',\n                'append_branch': 'amount_re',\n                'parser_path': '_extract_sparse_receipt_lines.amount_re',\n                'source_index': source_index,\n                'raw_line': raw_line,\n                'normalized_line': normalized,\n                'label': label,\n                'amount': _amount_to_float(amount),\n                'classification': label_classification,\n                'classification_allows_append': label_classification not in {'ignore', 'metadata', 'footer_payment_tax'},\n                'append_allowed': True,\n                'caller_line_hint': 'sparse amount_re extracted.append',\n            },\n        })\n"""


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} not found')
    raw = TARGET.read_text(encoding='utf-8')
    content, newline = normalize(raw)
    updated = content
    updated = replace_once(updated, CANONICAL_OLD, CANONICAL_NEW, 'canonical append trace')
    updated = replace_once(updated, SPARSE_QTY_OLD, SPARSE_QTY_NEW, 'sparse qty append trace')
    updated = replace_once(updated, SPARSE_AMOUNT_OLD, SPARSE_AMOUNT_NEW, 'sparse amount append trace')
    if updated == content:
        print('8K-T3 append trace was al aanwezig')
        return
    TARGET.write_text(restore(updated, newline), encoding='utf-8', newline='')
    print('8K-T3 append trace toegepast op backend/app/services/receipt_service.py')


if __name__ == '__main__':
    main()
