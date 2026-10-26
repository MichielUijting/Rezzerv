"""Explicit source-data correction of legacy deposits mislabelled as products.

Never a listing-time text fallback. No startup hook. Preserve amounts, labels,
links and stock history. Caller saves the complete plan before a transaction.
"""
from sqlalchemy import text
from app.receipt_ingestion.line_classifier import receipt_financial_candidate_line_type
from app.maintenance.repair_weight_detail_rows import plan_digest


def build_plan(conn, lock=False):
    rows = conn.execute(text('''
        SELECT rtl.id, rtl.receipt_table_id, rtl.raw_label, rtl.normalized_label,
               rtl.line_total, rtl.unit_price, rtl.quantity, rtl.line_role,
               rtl.inventory_eligible, rtl.is_deleted, rtl.matched_article_id,
               rtl.matched_global_product_id, rt.household_id, rt.approved_at
        FROM receipt_table_lines rtl JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
        WHERE rtl.line_role='product' AND rtl.inventory_eligible=1
          AND COALESCE(rtl.is_deleted,FALSE)=FALSE
        ORDER BY rtl.receipt_table_id, rtl.id
    ''' + (' FOR UPDATE OF rtl, rt' if lock else ''))).mappings().all()
    plan = []
    for raw in rows:
        row = dict(raw)
        if row['line_role'] != 'product' or row['inventory_eligible'] != 1 or row['is_deleted']:
            continue
        if row['line_total'] is None:
            continue
        # Apply the same source classifier to both original and normalized
        # evidence. A conflicting product description is never overwritten.
        labels = (row['raw_label'], row['normalized_label'] or row['raw_label'])
        if not all(receipt_financial_candidate_line_type(label, has_amount=True) == 'deposit' for label in labels):
            continue
        plan.append({'id': row['id'], 'receipt_table_id': row['receipt_table_id'],
                     'household_id': row['household_id'], 'source_snapshot': row})
    return plan


def apply_plan(conn, expected_digest):
    plan = build_plan(conn, lock=True)
    if plan_digest(plan) != expected_digest:
        raise ValueError('De statiegeldgegevens zijn gewijzigd sinds de veiligheidskopie. Geen herstel uitgevoerd.')
    for item in plan:
        result = conn.execute(text('''UPDATE receipt_table_lines
            SET line_role='financial', inventory_eligible=0
            WHERE id=:id AND receipt_table_id=:receipt
              AND line_role='product' AND inventory_eligible=1
              AND COALESCE(is_deleted,FALSE)=FALSE
              AND EXISTS (SELECT 1 FROM receipt_tables rt
                          WHERE rt.id=:receipt AND rt.household_id=:household)
        '''), {'id': item['id'], 'receipt': item['receipt_table_id'], 'household': item['household_id']})
        if result.rowcount != 1:
            raise ValueError('Statiegeldregel gewijzigd tijdens herstel; gehele transactie terugdraaien.')
    return len(plan)


def build_purchase_plan(conn, lock=False):
    """Unprocessed standalone legacy imports are product DTOs, not a ledger.

    Preserve their complete original source in the host backup before removing
    an incorrectly admitted deposit. Linked/processed evidence fails closed.
    """
    rows = conn.execute(text('''
        SELECT pil.*, pib.household_id, pib.raw_payload AS batch_source_snapshot
        FROM purchase_import_lines pil JOIN purchase_import_batches pib ON pib.id=pil.batch_id
        WHERE pib.source_type <> 'receipt'
          AND COALESCE(pil.external_line_ref,'') NOT LIKE 'receipt-line:%'
          AND pil.processed_event_id IS NULL AND pil.processed_at IS NULL
          AND COALESCE(pil.processing_status,'pending')='pending'
          AND pil.matched_global_product_id IS NULL AND pil.matched_household_article_id IS NULL
          AND pil.matched_global_article_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM external_product_candidates epc
                          WHERE epc.purchase_import_line_id=pil.id)
        ORDER BY pil.batch_id, pil.id
    ''' + (' FOR UPDATE OF pil, pib' if lock else ''))).mappings().all()
    plan = []
    for raw in rows:
        row = dict(raw)
        if row['line_price_raw'] is None:
            continue
        if receipt_financial_candidate_line_type(row['article_name_raw'], has_amount=True) != 'deposit':
            continue
        plan.append({'id': row['id'], 'batch_id': row['batch_id'],
                     'household_id': row['household_id'], 'source_snapshot': row})
    return plan


def apply_purchase_plan(conn, expected_digest):
    plan = build_purchase_plan(conn, lock=True)
    if plan_digest(plan) != expected_digest:
        raise ValueError('De importgegevens zijn gewijzigd sinds de veiligheidskopie. Geen herstel uitgevoerd.')
    for item in plan:
        result = conn.execute(text('''DELETE FROM purchase_import_lines
            WHERE id=:id AND batch_id=:batch AND processed_event_id IS NULL AND processed_at IS NULL
              AND matched_global_product_id IS NULL AND matched_household_article_id IS NULL
              AND matched_global_article_id IS NULL
              AND EXISTS (SELECT 1 FROM purchase_import_batches pib
                          WHERE pib.id=:batch AND pib.household_id=:household)
        '''), {'id': item['id'], 'batch': item['batch_id'], 'household': item['household_id']})
        if result.rowcount != 1:
            raise ValueError('Importregel gewijzigd tijdens herstel; gehele transactie terugdraaien.')
    return len(plan)
