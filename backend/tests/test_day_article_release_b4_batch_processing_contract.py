from pathlib import Path


SOURCE = Path('app/services/day_article_batch_processing_service.py').read_text(encoding='utf-8')
MAIN_SOURCE = Path('app/main.py').read_text(encoding='utf-8')


def test_b4_resolves_line_override_before_article_default():
    assert 'override = get_line_inventory_handling_override' in SOURCE
    assert 'if override:' in SOURCE
    assert 'get_default_inventory_handling' in SOURCE


def test_b4_uses_purchase_import_line_as_idempotency_key():
    assert 'idempotency_key=f"purchase-import-line:{str(line_id)}"' in SOURCE


def test_b4_marks_direct_line_as_inventory_mutation_skipped():
    assert '"inventory_mutation_skipped": True' in SOURCE


def test_b4_must_be_wired_into_batch_processor():
    assert 'resolve_effective_line_inventory_handling' in MAIN_SOURCE
    assert 'process_direct_purchase_import_line' in MAIN_SOURCE
    assert 'inventory_mutation_skipped' in MAIN_SOURCE


def test_b4_marks_line_processed_and_skips_normal_inventory_path():
    assert "effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION" in MAIN_SOURCE
    assert '"inventory_mutation_skipped": True' in MAIN_SOURCE
    assert "processed_count += 1" in MAIN_SOURCE
    assert "continue" in MAIN_SOURCE


def test_b4_keeps_stable_event_ids_for_idempotent_replay():
    day_service = Path('app/services/day_article_service.py').read_text(encoding='utf-8')
    assert 'receipt_event_id' in day_service
    assert 'direct_consumption_event_id' in day_service


def test_b4_direct_purchase_keeps_financial_event_but_skips_stock_mutation():
    function_start = MAIN_SOURCE.index('def process_purchase_import_batch(')
    direct_start = MAIN_SOURCE.index('if effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION:', function_start)
    direct_end = MAIN_SOURCE.index('                auto_consume_decision = determine_auto_consume_decision(', direct_start)
    direct_branch = MAIN_SOURCE[direct_start:direct_end]
    assert 'direct_purchase_event_id = create_inventory_purchase_event(' in direct_branch
    assert 'price=float(line.get("line_price_raw"))' in direct_branch
    assert 'currency=line.get("currency_code") or "EUR"' in direct_branch
    assert 'purchase_date=purchase_date' in direct_branch
    assert 'apply_inventory_purchase(' not in direct_branch
    assert '"financial_purchase_registered": True' in direct_branch


def test_b4_removes_obsolete_direct_inventory_artifacts():
    assert 'remove_direct_inventory_artifacts' in MAIN_SOURCE
    assert 'DELETE FROM inventory' in SOURCE
    assert 'Direct is a processing destination, never a stock-holding location' in SOURCE
