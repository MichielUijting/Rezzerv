from pathlib import Path

p = Path(r"C:\Users\Gebruiker\Rezzerv_Github\backend\app\testing_receipt_line_diagnosis_routes.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    "from app.services.receipt_service import parse_receipt_content, _classify_receipt_text_line\n",
    "from app.services.receipt_service import parse_receipt_content, _classify_receipt_text_line\n"
    "from app.receipt_ingestion.line_classifier import diagnose_article_line_classification\n",
)

old = """def _diagnostic_line_classification(value: Any, *, store_name: str | None, filename: str | None) -> str:
    try:
        return _classify_receipt_text_line(str(value or ''), store_name=store_name, filename=filename)
    except Exception as exc:
        return f'classification_error:{exc.__class__.__name__}'
"""

new = """def _diagnostic_line_diagnosis(value: Any, *, store_name: str | None, filename: str | None) -> dict[str, Any]:
    try:
        return diagnose_article_line_classification(
            str(value or ''),
            store_name=store_name,
            filename=filename,
        )
    except Exception as exc:
        fallback = f'classification_error:{exc.__class__.__name__}'
        return {
            'raw_line': value,
            'normalized_line': str(value or '').strip(),
            'store_name': store_name,
            'filename': filename,
            'classification': fallback,
            'article_decision': 'GEEN_ARTIKEL',
            'include_in_article_sum': False,
            'reason': fallback,
            'rule': 'DIAGNOSIS_EXCEPTION',
            'stage': 'diagnosis_error',
            'matched': None,
            'trace': {'classification': fallback},
            'extra_context': {},
        }


def _diagnostic_line_classification(value: Any, *, store_name: str | None, filename: str | None) -> str:
    return str(_diagnostic_line_diagnosis(value, store_name=store_name, filename=filename).get('classification') or 'ignore')
"""

if old not in s:
    raise SystemExit("R9-23B patchpunt 1 niet gevonden")

s = s.replace(old, new, 1)

old2 = """def _build_producer_trace(line: dict[str, Any], *, filename: str, store_name: str | None) -> dict[str, Any]:
    existing_trace = line.get('producer_trace') if isinstance(line.get('producer_trace'), dict) else {}
    label = line.get('normalized_label') or line.get('raw_label')
    classification = existing_trace.get('classification') or _diagnostic_line_classification(label, store_name=store_name, filename=filename)
    return {
        'filename': existing_trace.get('filename') or filename,
        'store_name': existing_trace.get('store_name') or store_name,
        'parser_path': existing_trace.get('parser_path') or 'parse_receipt_content.result_line',
        'source_index': existing_trace.get('source_index') if 'source_index' in existing_trace else line.get('source_index'),
        'normalized_line': existing_trace.get('normalized_line') or line.get('normalized_label') or line.get('raw_label'),
        'label': existing_trace.get('label') or label,
        'amount': _to_number(existing_trace.get('amount') if 'amount' in existing_trace else line.get('line_total')),
        'classification': classification,
        'append_allowed': existing_trace.get('append_allowed') if 'append_allowed' in existing_trace else True,
        'classification_allows_append': classification not in {'ignore', 'metadata', 'footer_payment_tax'},
        'trace_source': 'parser_trace' if existing_trace else 'diagnostic_result_line_trace',
    }
"""

new2 = """def _build_producer_trace(line: dict[str, Any], *, filename: str, store_name: str | None) -> dict[str, Any]:
    existing_trace = line.get('producer_trace') if isinstance(line.get('producer_trace'), dict) else {}
    label = line.get('normalized_label') or line.get('raw_label')
    diagnosis = _diagnostic_line_diagnosis(label, store_name=store_name, filename=filename)

    classification = existing_trace.get('classification') or diagnosis.get('classification')
    rule = existing_trace.get('classification_rule') or diagnosis.get('rule')
    stage = existing_trace.get('classification_stage') or diagnosis.get('stage')
    matched = existing_trace.get('classification_matched') or diagnosis.get('matched')
    trace = existing_trace.get('classification_trace') or diagnosis.get('trace')

    return {
        'filename': existing_trace.get('filename') or filename,
        'store_name': existing_trace.get('store_name') or store_name,
        'parser_path': existing_trace.get('parser_path') or 'parse_receipt_content.result_line',
        'source_index': existing_trace.get('source_index') if 'source_index' in existing_trace else line.get('source_index'),
        'normalized_line': existing_trace.get('normalized_line') or line.get('normalized_label') or line.get('raw_label'),
        'label': existing_trace.get('label') or label,
        'amount': _to_number(existing_trace.get('amount') if 'amount' in existing_trace else line.get('line_total')),
        'classification': classification,
        'classification_rule': rule,
        'classification_stage': stage,
        'classification_matched': matched,
        'classification_trace': trace,
        'article_decision': diagnosis.get('article_decision'),
        'include_in_article_sum': diagnosis.get('include_in_article_sum'),
        'reason': diagnosis.get('reason'),
        'append_allowed': existing_trace.get('append_allowed') if 'append_allowed' in existing_trace else True,
        'classification_allows_append': classification not in {'ignore', 'metadata', 'footer_payment_tax'},
        'trace_source': 'parser_trace_plus_existing_line_diagnosis' if existing_trace else 'existing_line_diagnosis',
    }
"""

if old2 not in s:
    raise SystemExit("R9-23B patchpunt 2 niet gevonden")

s = s.replace(old2, new2, 1)

p.write_text(s, encoding="utf-8")
print("R9-23B toegepast: bestaande receipt-line-diagnosis gebruikt diagnose_article_line_classification.")
print("Aangepast: backend/app/testing_receipt_line_diagnosis_routes.py")
