"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Backend automated test
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: keep_diagnostic
"""

from app.receipt_ingestion.parser_diagnostics import (
    diagnostic_events_from_lines,
    normalize_producer_trace,
    summarize_lines_parser_diagnostics,
    summarize_parser_diagnostics,
)


def test_normalize_producer_trace_maps_core_fields():
    event = normalize_producer_trace(
        {
            'parser_path': '_extract_receipt_lines.append_line',
            'append_branch': 'append_line',
            'classification': 'product_candidate',
            'classification_allows_append': True,
            'append_allowed': True,
            'source_index': '7',
            'raw_line': 'MELK 1,89',
            'normalized_line': 'MELK 1,89',
            'label': 'MELK',
            'amount': '1.89',
            'filename': 'receipt.jpg',
            'store_name': 'Jumbo',
            'function_name': '_extract_receipt_lines',
            'caller_line_hint': 'test hint',
        }
    )

    assert event.parser_path == '_extract_receipt_lines.append_line'
    assert event.append_branch == 'append_line'
    assert event.classification == 'product_candidate'
    assert event.append_allowed is True
    assert event.blocked_reason is None
    assert event.source_index == 7
    assert event.label == 'MELK'
    assert event.amount == 1.89


def test_normalize_producer_trace_derives_blocked_reason_from_append_allowed():
    event = normalize_producer_trace(
        {
            'classification': 'metadata',
            'classification_allows_append': False,
            'append_allowed': False,
        }
    )

    assert event.append_allowed is False
    assert event.blocked_reason == 'append_not_allowed'


def test_diagnostic_events_from_lines_ignores_lines_without_trace():
    lines = [
        {'raw_label': 'MELK'},
        {
            'raw_label': 'BROOD',
            'producer_trace': {
                'append_branch': 'append_line',
                'classification': 'product_candidate',
                'append_allowed': True,
            },
        },
    ]

    events = diagnostic_events_from_lines(lines)

    assert len(events) == 1
    assert events[0].append_branch == 'append_line'


def test_summarize_parser_diagnostics_counts_branches_and_classifications():
    events = diagnostic_events_from_lines(
        [
            {
                'producer_trace': {
                    'append_branch': 'append_line',
                    'classification': 'product_candidate',
                    'append_allowed': True,
                }
            },
            {
                'producer_trace': {
                    'append_branch': 'amount_re',
                    'classification': 'product_candidate',
                    'append_allowed': True,
                }
            },
            {
                'producer_trace': {
                    'append_branch': 'blocked_footer',
                    'classification': 'footer_payment_tax',
                    'classification_allows_append': False,
                    'append_allowed': False,
                }
            },
        ]
    )

    summary = summarize_parser_diagnostics(events)

    assert summary['total_candidates'] == 3
    assert summary['appended_candidates'] == 2
    assert summary['blocked_candidates'] == 1
    assert summary['by_branch']['append_line'] == 1
    assert summary['by_branch']['amount_re'] == 1
    assert summary['by_classification']['product_candidate'] == 2
    assert summary['by_classification']['footer_payment_tax'] == 1
    assert summary['by_blocked_reason']['append_not_allowed'] == 1


def test_summarize_lines_parser_diagnostics_empty_is_safe():
    summary = summarize_lines_parser_diagnostics([])

    assert summary == {
        'total_candidates': 0,
        'appended_candidates': 0,
        'blocked_candidates': 0,
        'by_branch': {},
        'by_classification': {},
        'by_blocked_reason': {},
    }


def test_parser_diagnostics_summary_does_not_mutate_lines_or_status_value():
    parse_status = 'parsed'
    lines = [
        {
            'raw_label': 'MELK',
            'producer_trace': {
                'append_branch': 'append_line',
                'classification': 'product_candidate',
                'append_allowed': True,
            },
        }
    ]
    before = [dict(line) for line in lines]

    summary = summarize_lines_parser_diagnostics(lines)

    assert parse_status == 'parsed'
    assert lines == before
    assert summary['total_candidates'] == 1
    assert summary['by_branch'] == {'append_line': 1}
