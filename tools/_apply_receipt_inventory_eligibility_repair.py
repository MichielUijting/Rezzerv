from pathlib import Path

classifier_path = Path('backend/app/receipt_ingestion/line_classifier.py')
main_path = Path('backend/app/main.py')
test_path = Path('backend/tests/test_receipt_inventory_eligibility.py')
contract_path = Path('backend/app/testing/unpack_copies_kassa_contract.py')

classifier = classifier_path.read_text(encoding='utf-8')
main = main_path.read_text(encoding='utf-8')
contract = contract_path.read_text(encoding='utf-8')

old_import = '''from app.receipt_ingestion.spaarzegels_terms import (
    contains_spaarzegels_metadata_token,
    contains_spaarzegels_priced_token,
    matches_spaarzegels_value_label,
    spaarzegels_metadata_tokens,
)'''
new_import = '''from app.receipt_ingestion.spaarzegels_terms import (
    contains_spaarzegels_metadata_token,
    contains_spaarzegels_priced_token,
    is_spaarzegels_flow_excluded,
    matches_spaarzegels_value_label,
    spaarzegels_metadata_tokens,
)'''
assert old_import in classifier
classifier = classifier.replace(old_import, new_import, 1)

old_tokens = '''GENERIC_DEPOSIT_RETURN_TOKENS = (
    'statiegeld retour', 'retour statiegeld', 'emballage retour', 'fust retour',
)'''
new_tokens = '''GENERIC_NON_INVENTORY_CHARGE_TOKENS = (
    'statiegeld retour', 'retour statiegeld', 'emballage retour', 'fust retour',
    'statiegeld', 'emballage', 'fust',
    'verzendkosten', 'verzend kosten', 'bezorgkosten', 'bezorg kosten',
    'shipping fee', 'delivery fee',
)'''
assert old_tokens in classifier
classifier = classifier.replace(old_tokens, new_tokens, 1)
classifier = classifier.replace('GENERIC_DEPOSIT_RETURN_TOKENS', 'GENERIC_NON_INVENTORY_CHARGE_TOKENS')

old_reason = "if any(token in lowered for token in ('statiegeld retour', 'retour statiegeld', 'emballage retour')):\n            return 'deposit_return_or_refund_line'"
new_reason = "if _token_match(lowered, GENERIC_NON_INVENTORY_CHARGE_TOKENS):\n            return 'non_inventory_charge_or_deposit_line'"
assert old_reason in classifier
classifier = classifier.replace(old_reason, new_reason, 1)

helper_anchor = '''def classification_allows_append(classification: str | None) -> bool:
    return str(classification or '') in (ARTICLE_CLASSIFICATIONS | {'continuation'})'''
assert helper_anchor in classifier
helper = '''NON_INVENTORY_PRODUCT_RULES = frozenset({
    'GENERIC_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
    'PLUS_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
    'GENERIC_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
    'STORE_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
})


def receipt_line_is_inventory_eligible(
    line: dict[str, Any],
    *,
    store_name: str | None = None,
    filename: str | None = None,
) -> bool:
    """Return True only for receipt-table rows that may enter Uitpakken/Voorraad."""
    if not isinstance(line, dict):
        return False
    raw_label = str(
        line.get('corrected_raw_label')
        or line.get('raw_label')
        or line.get('normalized_label')
        or ''
    ).strip()
    if not raw_label:
        return False
    if is_spaarzegels_flow_excluded({
        'receipt_line_text': raw_label,
        'raw_label': raw_label,
        'normalized_label': line.get('normalized_label'),
        'quantity_label': line.get('quantity_label'),
        'quantity': line.get('quantity'),
        'unit_price': line.get('unit_price'),
        'line_total': line.get('line_total'),
        'price': line.get('line_total'),
    }):
        return False

    decision = _generic_non_article_trace(raw_label)
    if decision is None:
        decision = _store_specific_non_article_trace(
            raw_label,
            store_name=store_name,
            filename=filename,
        )
    if decision is None:
        return True

    classification = str(decision.get('classification') or 'ignore')
    rule = str(decision.get('rule') or '')
    if rule in NON_INVENTORY_PRODUCT_RULES:
        return False
    return classification == 'product_candidate'


'''
classifier = classifier.replace(helper_anchor, helper + helper_anchor, 1)
assert 'GENERIC_DEPOSIT_RETURN_TOKENS' not in classifier
classifier_path.write_text(classifier, encoding='utf-8')

import_anchor = 'from app.services.receipt_reimport_lineage_service import get_prior_processed_line_fact\n'
new_main_import = 'from app.receipt_ingestion.line_classifier import receipt_line_is_inventory_eligible\n'
assert import_anchor in main
assert new_main_import not in main
main = main.replace(import_anchor, import_anchor + new_main_import, 1)

old_existing = '''    existing_refs = {
        str(row[0] or '').strip()
        for row in conn.execute(
            text("SELECT external_line_ref FROM purchase_import_lines WHERE batch_id = :batch_id"),
            {'batch_id': batch_id},
        ).fetchall()
        if str(row[0] or '').strip()
    }'''
new_existing = '''    existing_refs = {
        str(row.get('external_line_ref') or '').strip(): {
            'id': str(row.get('id') or '').strip(),
            'processed_event_id': str(row.get('processed_event_id') or '').strip() or None,
        }
        for row in conn.execute(
            text(
                "SELECT id, external_line_ref, processed_event_id "
                "FROM purchase_import_lines WHERE batch_id = :batch_id"
            ),
            {'batch_id': batch_id},
        ).mappings().all()
        if str(row.get('external_line_ref') or '').strip()
    }'''
assert old_existing in main
main = main.replace(old_existing, new_existing, 1)

line_rows_anchor = '''    inserted = 0
    household_id = str((receipt or {}).get('household_id') or '').strip()
    for offset, line in enumerate(line_rows, start=1):'''
replacement = '''    source_refs = {
        f"receipt-line:{line.get('id')}"
        for line in line_rows
        if str(line.get('id') or '').strip()
    }
    for stale_ref, stale in list(existing_refs.items()):
        if stale_ref.startswith('receipt-line:') and stale_ref not in source_refs and not stale.get('processed_event_id'):
            conn.execute(
                text("DELETE FROM purchase_import_lines WHERE id = :id AND batch_id = :batch_id"),
                {'id': stale.get('id'), 'batch_id': batch_id},
            )
            existing_refs.pop(stale_ref, None)

    inserted = 0
    household_id = str((receipt or {}).get('household_id') or '').strip()
    for offset, line in enumerate(line_rows, start=1):'''
assert line_rows_anchor in main
main = main.replace(line_rows_anchor, replacement, 1)

gate_anchor = '''        external_line_ref = f"receipt-line:{line.get('id') or offset}"
        prior_processed = get_prior_processed_line_fact(
            conn, line.get('logical_line_key'), current_receipt_table_id=receipt_table_id
        )'''
gated = '''        external_line_ref = f"receipt-line:{line.get('id') or offset}"
        existing_line = existing_refs.get(external_line_ref)
        inventory_eligible = receipt_line_is_inventory_eligible(
            dict(line),
            store_name=str((receipt or {}).get('store_name') or '').strip() or None,
        )
        if not inventory_eligible:
            if existing_line and not existing_line.get('processed_event_id'):
                conn.execute(
                    text("DELETE FROM purchase_import_lines WHERE id = :id AND batch_id = :batch_id"),
                    {'id': existing_line.get('id'), 'batch_id': batch_id},
                )
                existing_refs.pop(external_line_ref, None)
            elif existing_line:
                conn.execute(
                    text(
                        "UPDATE purchase_import_lines "
                        "SET review_decision = 'ignored', updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = :id AND batch_id = :batch_id"
                    ),
                    {'id': existing_line.get('id'), 'batch_id': batch_id},
                )
            continue
        prior_processed = get_prior_processed_line_fact(
            conn, line.get('logical_line_key'), current_receipt_table_id=receipt_table_id
        )'''
assert gate_anchor in main
main = main.replace(gate_anchor, gated, 1)

assert 'if external_line_ref in existing_refs:' in main
main = main.replace('if external_line_ref in existing_refs:', 'if existing_line:', 1)
old_add = '''        existing_refs.add(external_line_ref)
        inserted += 1'''
new_add = '''        existing_refs[external_line_ref] = {
            'id': '',
            'processed_event_id': (prior_processed or {}).get('processed_event_id'),
        }
        inserted += 1'''
assert old_add in main
main = main.replace(old_add, new_add, 1)
main_path.write_text(main, encoding='utf-8')

contract_token = '''require(
    "matched_global_product_id = (" in sync_block
    and "str(line.get('matched_global_product_id') or '').strip()" in sync_block,
    "Uitpakken kopieert matched_global_product_id niet letterlijk uit Kassa",
)'''
assert contract_token in contract
gate_contract = '''require(
    "receipt_line_is_inventory_eligible(" in sync_block,
    "Uitpakken mist de centrale voorraadgeschiktheidsgate",
)
require(
    "DELETE FROM purchase_import_lines" in sync_block,
    "Uitpakken ruimt dode, niet-verwerkte purchase-importregels niet op",
)
'''
contract = contract.replace(contract_token, gate_contract + contract_token, 1)
contract_path.write_text(contract, encoding='utf-8')

test_path.write_text('''from app.receipt_ingestion.line_classifier import receipt_line_is_inventory_eligible


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
''', encoding='utf-8')

print('RECEIPT_INVENTORY_ELIGIBILITY_REPAIR_APPLIED')
