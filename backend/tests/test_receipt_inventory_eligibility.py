from app.receipt_ingestion.line_classifier import receipt_line_is_inventory_eligible


def eligible(label: str, **extra) -> bool:
    store_name = extra.pop('store_name', None)
    row = {'raw_label': label, 'line_total': extra.pop('line_total', None), **extra}
    return receipt_line_is_inventory_eligible(row, store_name=store_name)


def test_physical_articles_remain_inventory_eligible():
    assert eligible('Halfvolle melk') is True
    assert eligible('Onbekend fysiek artikel') is True
    assert eligible('Tempranillo Cabernet Sauvignon') is True


def test_savings_stamps_never_enter_unpacking():
    assert eligible('10 KOOPZEGELS 1,00', line_total=1.00) is False
    assert eligible('Koopzegels', line_total=0.20, quantity=2, unit_price=0.10) is False


def test_non_inventory_charges_never_enter_unpacking():
    for label in (
        'Statiegeld 0,25',
        'Emballage 0,50',
        'Fust retour -1,00',
        'Verzendkosten 4,95',
        'Verzend kosten 4,95',
        'Bezorgkosten 2,99',
        'Delivery fee 3,50',
    ):
        assert eligible(label) is False, label


def test_financial_and_footer_lines_never_enter_unpacking():
    for label in (
        'Korting 1,00',
        'Bonus 0,50',
        'Totaal 23,45',
        'Betaald 23,45',
        'BTW 9% 1,23',
    ):
        assert eligible(label) is False, label
