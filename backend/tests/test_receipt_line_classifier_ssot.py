import re

from app.receipt_ingestion.line_classifier import (
    classification_allows_append,
    diagnose_article_line_classification,
    trace_receipt_text_line_classification,
)


LABEL_FIRST_RE = re.compile(
    r'^(?P<label>(?=[A-Za-z0-9].*[A-Za-z])[A-Za-z0-9].*?)\s+'
    r'(?:(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s*[xX]\s+)?'
    r'(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
    r'(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?'
    r'(?:\s+(?:EUR|[A-Z]{1,3}))?$',
    re.IGNORECASE,
)


def test_gateway_allows_only_standalone_product_candidates():
    assert classification_allows_append('product_candidate') is True
    assert classification_allows_append('amount_detail') is False
    assert classification_allows_append('continuation') is False
    assert classification_allows_append('metadata') is False
    assert classification_allows_append('footer_payment_tax') is False
    assert classification_allows_append('ignore') is False


def test_prijs_per_kg_is_supporting_detail_not_standalone_article():
    diagnosis = diagnose_article_line_classification(
        'Prijs per kg 2,29',
        store_name='Albert Heijn',
        filename='AH foto 11.jpeg',
        label_first_re=LABEL_FIRST_RE,
    )

    assert diagnosis['classification'] == 'amount_detail'
    assert diagnosis['article_decision'] == 'ONDERSTEUNENDE_ARTIKELINFO'
    assert diagnosis['include_in_article_sum'] is False
    assert diagnosis['reason'] == 'supporting_amount_detail_not_standalone_article'
    assert diagnosis['rule'] == 'GENERIC_SUPPORTING_AMOUNT_DETAIL_TOKEN'


def test_prijs_per_kg_with_product_label_is_still_supporting_detail():
    diagnosis = diagnose_article_line_classification(
        'Prijs per kg KOMKOMMER 2,29',
        store_name='Albert Heijn',
        filename='AH foto 11.jpeg',
        label_first_re=LABEL_FIRST_RE,
    )

    assert diagnosis['classification'] == 'amount_detail'
    assert diagnosis['include_in_article_sum'] is False


def test_statiegeld_value_line_remains_product_candidate_when_it_has_amount():
    trace = trace_receipt_text_line_classification(
        'STATIEGELD 0,60',
        store_name='Albert Heijn',
        filename='AH foto 11.jpeg',
        label_first_re=LABEL_FIRST_RE,
    )

    assert trace['classification'] == 'product_candidate'
    assert classification_allows_append(trace['classification']) is True


def test_koopzegels_value_line_remains_appendable_financial_line():
    trace = trace_receipt_text_line_classification(
        '130 KOOPZEGELS PREMIUM 13,00',
        store_name='Albert Heijn',
        filename='AH foto 17.jpeg',
        label_first_re=LABEL_FIRST_RE,
    )

    assert trace['classification'] == 'product_candidate'
    assert classification_allows_append(trace['classification']) is True
