import re

from backend.receipt_ingestion.line_classifier import (
    classification_allows_append,
    classify_receipt_text_line,
)


DETAIL_ONLY_RE = re.compile(
    r'^(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))$'
)
QTY_FIRST_RE = re.compile(
    r'^(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<label>.+?)\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))$'
)
LABEL_FIRST_RE = re.compile(
    r'^(?P<label>.+?)\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))$'
)


def classify(value: str) -> str:
    return classify_receipt_text_line(
        value,
        detail_only_re=DETAIL_ONLY_RE,
        qty_first_re=QTY_FIRST_RE,
        label_first_re=LABEL_FIRST_RE,
    )


def test_za_opening_time_line_is_metadata():
    assert classify('ZA 8.00') == 'metadata'


def test_zo_opening_time_line_is_metadata():
    assert classify('ZO 12.00') == 'metadata'


def test_zon_opening_time_line_is_metadata():
    assert classify('ZON 10.00') == 'metadata'


def test_vat_footer_line_is_footer_payment_tax():
    assert classify('B 9,00% 4,59 0,41') == 'footer_payment_tax'


def test_weekday_range_line_is_metadata():
    assert classify('Maandag t/m Woernsdag') == 'metadata'


def test_loose_decimal_amount_is_footer_payment_tax():
    assert classify('50.89') == 'footer_payment_tax'


def test_zegels_noise_line_is_footer_payment_tax():
    assert classify('zege1s + 12:10 999') == 'footer_payment_tax'


def test_label_first_product_line_is_product_candidate():
    assert classify('MELK 1,89') == 'product_candidate'


def test_qty_first_product_line_is_product_candidate():
    assert classify('2 MELK 3,78') == 'product_candidate'


def test_amount_detail_line_is_amount_detail():
    assert classify('2 x 1,89') == 'amount_detail'


def test_blocking_classifications_do_not_allow_append():
    assert not classification_allows_append('ignore')
    assert not classification_allows_append('metadata')
    assert not classification_allows_append('footer_payment_tax')


def test_product_classifications_allow_append():
    assert classification_allows_append('product_candidate')
    assert classification_allows_append('amount_detail')
    assert classification_allows_append('continuation')
