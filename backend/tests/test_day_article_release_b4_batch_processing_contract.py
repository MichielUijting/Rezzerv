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
