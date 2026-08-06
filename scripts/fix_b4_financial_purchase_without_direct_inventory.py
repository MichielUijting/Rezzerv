from pathlib import Path

MAIN = Path('backend/app/main.py')
BATCH_SERVICE = Path('backend/app/services/day_article_batch_processing_service.py')
CONTRACT = Path('backend/tests/test_day_article_release_b4_batch_processing_contract.py')

main = MAIN.read_text(encoding='utf-8')
service = BATCH_SERVICE.read_text(encoding='utf-8')
contract = CONTRACT.read_text(encoding='utf-8')

old_block = '''                effective_inventory_handling = resolve_effective_line_inventory_handling(
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

                article_name = article["name"]
                note = build_store_import_note(batch["store_provider_code"], batch_id, line_id, line["article_name_raw"])
                pre_purchase_total = get_article_total_quantity(conn, batch["household_id"], article_name)
'''

new_block = '''                article_name = article["name"]
                note = build_store_import_note(batch["store_provider_code"], batch_id, line_id, line["article_name_raw"])
                pre_purchase_total = get_article_total_quantity(conn, batch["household_id"], article_name)
                effective_inventory_handling = resolve_effective_line_inventory_handling(
                    conn,
                    household_id=str(batch["household_id"]),
                    household_article_id=str(article_id),
                    line_id=str(line_id),
                )
                if effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION:
                    current_stage = 'direct_purchase_financial_event_write'
                    direct_purchase_event_id = create_inventory_purchase_event(
                        conn,
                        batch["household_id"],
                        article_id,
                        article_name,
                        quantity,
                        resolved_location,
                        note,
                        supplier_name=batch.get("store_name") or batch.get("store_label") or batch.get("store_provider_name") or batch.get("store_provider_code"),
                        price=float(line.get("line_price_raw")) if line.get("line_price_raw") is not None else None,
                        currency=line.get("currency_code") or "EUR",
                        purchase_date=purchase_date,
                        article_number=line.get("external_article_code"),
                        barcode=line.get("barcode") or None,
                    )
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
                    removed_direct_inventory_rows = remove_direct_inventory_artifacts(
                        conn,
                        household_id=str(batch["household_id"]),
                        household_article_id=str(article_id),
                    )
                    sync_household_article_price_metrics(
                        conn,
                        batch["household_id"],
                        article_id,
                        ensure_household_article_global_product_link(conn, article_id, line.get("barcode") or None),
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
                            "event_id": direct_purchase_event_id,
                            "final_location_id": resolved_location["location_id"],
                            "id": line_id,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE household_articles
                            SET article_group_id = :article_group_id,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :article_id
                              AND household_id = :household_id
                            """
                        ),
                        {
                            "article_group_id": article_group_id,
                            "article_id": str(article_id),
                            "household_id": str(batch["household_id"]),
                        },
                    )
                    results.append({
                        "line_id": line_id,
                        "line_reference": line_reference,
                        "status": "processed",
                        "event_id": direct_purchase_event_id,
                        "financial_purchase_registered": True,
                        "inventory_mutation_skipped": True,
                        "removed_direct_inventory_rows": removed_direct_inventory_rows,
                        "direct_consumption": direct_result,
                        "message": "Aankoop financieel geregistreerd en direct verbruikt; bestaande voorraad ongewijzigd",
                    })
                    processed_count += 1
                    continue
'''

if old_block not in main:
    raise SystemExit('B4_OLD_DIRECT_BRANCH_NOT_FOUND')
main = main.replace(old_block, new_block, 1)

import_old = '''from app.services.day_article_batch_processing_service import (
    DIRECT_CONSUMPTION as DAY_ARTICLE_DIRECT_CONSUMPTION,
    process_direct_purchase_import_line,
    resolve_effective_line_inventory_handling,
)
'''
import_new = '''from app.services.day_article_batch_processing_service import (
    DIRECT_CONSUMPTION as DAY_ARTICLE_DIRECT_CONSUMPTION,
    process_direct_purchase_import_line,
    remove_direct_inventory_artifacts,
    resolve_effective_line_inventory_handling,
)
'''
if import_old not in main:
    raise SystemExit('B4_IMPORT_BLOCK_NOT_FOUND')
main = main.replace(import_old, import_new, 1)

cleanup_function = '''\n\ndef remove_direct_inventory_artifacts(\n    conn,\n    *,\n    household_id: str,\n    household_article_id: str,\n) -> int:\n    """Remove inventory rows that older B4 code incorrectly stored at Direct / Direct.\n\n    Direct is a processing destination, never a stock-holding location. Any\n    active inventory row there is therefore an invalid artifact.\n    """\n    direct_location = ensure_direct_location(conn, household_id)\n    result = conn.execute(\n        text(\n            """\n            DELETE FROM inventory\n            WHERE household_id = :household_id\n              AND household_article_id = :household_article_id\n              AND (space_id = :space_id OR sublocation_id = :sublocation_id)\n            """\n        ),\n        {\n            "household_id": str(household_id),\n            "household_article_id": str(household_article_id),\n            "space_id": direct_location["space_id"],\n            "sublocation_id": direct_location["sublocation_id"],\n        },\n    )\n    return int(result.rowcount or 0)\n'''

if 'def remove_direct_inventory_artifacts(' not in service:
    service += cleanup_function

contract_extra = '''\n\ndef test_b4_direct_purchase_keeps_financial_event_but_skips_stock_mutation():\n    function_start = MAIN_SOURCE.index('def process_purchase_import_batch(')\n    direct_start = MAIN_SOURCE.index('if effective_inventory_handling == DAY_ARTICLE_DIRECT_CONSUMPTION:', function_start)\n    direct_end = MAIN_SOURCE.index('                auto_consume_decision = determine_auto_consume_decision(', direct_start)\n    direct_branch = MAIN_SOURCE[direct_start:direct_end]\n    assert 'direct_purchase_event_id = create_inventory_purchase_event(' in direct_branch\n    assert 'price=float(line.get("line_price_raw"))' in direct_branch\n    assert 'currency=line.get("currency_code") or "EUR"' in direct_branch\n    assert 'purchase_date=purchase_date' in direct_branch\n    assert 'apply_inventory_purchase(' not in direct_branch\n    assert '"financial_purchase_registered": True' in direct_branch\n\n\ndef test_b4_removes_obsolete_direct_inventory_artifacts():\n    assert 'remove_direct_inventory_artifacts' in MAIN_SOURCE\n    assert 'DELETE FROM inventory' in SOURCE\n    assert 'Direct is a processing destination, never a stock-holding location' in SOURCE\n'''
if 'test_b4_direct_purchase_keeps_financial_event_but_skips_stock_mutation' not in contract:
    contract += contract_extra

MAIN.write_text(main, encoding='utf-8')
BATCH_SERVICE.write_text(service, encoding='utf-8')
CONTRACT.write_text(contract, encoding='utf-8')
print('B4_FINANCIAL_PURCHASE_WITHOUT_DIRECT_INVENTORY_APPLIED')
