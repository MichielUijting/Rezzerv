from pathlib import Path

MAIN = Path('backend/app/main.py')
SERVICE = Path('backend/app/services/day_article_service.py')
CONTRACT = Path('backend/tests/test_day_article_release_b4_batch_processing_contract.py')

main = MAIN.read_text(encoding='utf-8')
service = SERVICE.read_text(encoding='utf-8')
contract = CONTRACT.read_text(encoding='utf-8')

import_block = '''from app.services.day_article_batch_processing_service import (
    DIRECT_CONSUMPTION as DAY_ARTICLE_DIRECT_CONSUMPTION,
    process_direct_purchase_import_line,
    resolve_effective_line_inventory_handling,
)
'''
if import_block not in main:
    anchor = 'from app.services.household_context_adapter import household_context_from_runtime_context\n'
    if anchor not in main:
        raise SystemExit('B4_IMPORT_ANCHOR_NOT_FOUND')
    main = main.replace(anchor, anchor + import_block, 1)

# Return stable event ids from the idempotent day-article event pair.
old_return = '''    return {"household_id": str(household_id), "household_article_id": str(household_article_id),
            "article_name": article.get("naam"), "handling": DIRECT_CONSUMPTION,
            "quantity_received": str(amount), "quantity_consumed": str(amount),
            "net_inventory_change": "0", "idempotency_key": normalized_key,
            "idempotent_replay": int(existing or 0) > 0, **location}
'''
new_return = '''    event_rows = conn.execute(text("""
        SELECT id, event_type
        FROM day_article_processing_events
        WHERE household_id = :household_id AND idempotency_key = :idempotency_key
        ORDER BY CASE event_type WHEN 'RECEIPT' THEN 0 ELSE 1 END
    """), {
        "household_id": str(household_id),
        "idempotency_key": normalized_key,
    }).mappings().all()
    event_ids = {str(row.get("event_type") or ""): str(row.get("id") or "") for row in event_rows}
    return {"household_id": str(household_id), "household_article_id": str(household_article_id),
            "article_name": article.get("naam"), "handling": DIRECT_CONSUMPTION,
            "quantity_received": str(amount), "quantity_consumed": str(amount),
            "net_inventory_change": "0", "idempotency_key": normalized_key,
            "receipt_event_id": event_ids.get("RECEIPT") or None,
            "direct_consumption_event_id": event_ids.get("DIRECT_CONSUMPTION") or None,
            "idempotent_replay": int(existing or 0) > 0, **location}
'''
if new_return not in service:
    if old_return not in service:
        raise SystemExit('B4_SERVICE_RETURN_ANCHOR_NOT_FOUND')
    service = service.replace(old_return, new_return, 1)

function_start = main.find('def process_purchase_import_batch(')
if function_start < 0:
    raise SystemExit('B4_BATCH_FUNCTION_NOT_FOUND')
next_route = main.find('\n@app.', function_start + 20)
function_end = next_route if next_route >= 0 else len(main)
function_text = main[function_start:function_end]

branch = '''                effective_inventory_handling = resolve_effective_line_inventory_handling(
                    conn,
                    household_id=str(batch["household_id"]),
                    household_article_id=str(article_id),
                    line_id=str(line_id),
                )
                if effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION:
                    direct_actor_context = require_household_context(
                        authorization,
                        str(batch["household_id"]),
                    )
                    direct_result = process_direct_purchase_import_line(
                        conn,
                        household_id=str(batch["household_id"]),
                        household_article_id=str(article_id),
                        line_id=str(line_id),
                        quantity=quantity,
                        actor_user_id=str(
                            direct_actor_context.get("user_id")
                            or payload.processed_by
                            or "ui"
                        ),
                    )
                    direct_event_id = str(
                        direct_result.get("receipt_event_id")
                        or direct_result.get("direct_consumption_event_id")
                        or f"day-article:{line_id}"
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE purchase_import_lines
                            SET processing_status = 'processed',
                                processed_at = CURRENT_TIMESTAMP,
                                processed_event_id = :event_id,
                                processing_error = NULL,
                                final_location_id = :final_location_id,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {
                            "event_id": direct_event_id,
                            "final_location_id": resolved_location["location_id"],
                            "id": line_id,
                        },
                    )
                    results.append({
                        "line_id": line_id,
                        "line_reference": line_reference,
                        "status": "processed",
                        "event_id": direct_event_id,
                        "inventory_mutation_skipped": True,
                        "direct_consumption": direct_result,
                        "message": "Ontvangst direct verbruikt; bestaande voorraad ongewijzigd",
                    })
                    processed_count += 1
                    continue

'''
if branch not in function_text:
    anchor = '                article_name = article["name"]\n'
    if anchor not in function_text:
        raise SystemExit('B4_BATCH_INSERT_ANCHOR_NOT_FOUND')
    function_text = function_text.replace(anchor, branch + anchor, 1)
    main = main[:function_start] + function_text + main[function_end:]

extra_contract = '''

def test_b4_marks_line_processed_and_skips_normal_inventory_path():
    assert "effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION" in MAIN_SOURCE
    assert '"inventory_mutation_skipped": True' in MAIN_SOURCE
    assert "processed_count += 1" in MAIN_SOURCE
    assert "continue" in MAIN_SOURCE


def test_b4_keeps_stable_event_ids_for_idempotent_replay():
    day_service = Path('app/services/day_article_service.py').read_text(encoding='utf-8')
    assert 'receipt_event_id' in day_service
    assert 'direct_consumption_event_id' in day_service
'''
if 'test_b4_marks_line_processed_and_skips_normal_inventory_path' not in contract:
    contract += extra_contract

MAIN.write_text(main, encoding='utf-8')
SERVICE.write_text(service, encoding='utf-8')
CONTRACT.write_text(contract, encoding='utf-8')
print('B4_DIRECT_BATCH_PROCESSING_INTEGRATED')
