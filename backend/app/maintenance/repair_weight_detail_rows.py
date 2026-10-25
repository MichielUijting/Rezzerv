"""Explicit, idempotent cleanup of proven duplicate legacy source rows.

No startup hook. Never deletes products, household articles or stock by name.
Caller must persist a plan backup before invoking apply_plan in a transaction.
"""
import hashlib
import json
from sqlalchemy import text
from app.receipt_ingestion.weight_detail import confirmed_weight_continuation


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()


def build_plan(conn, lock=False):
    # Lock source/parent facts during apply; no name-based link traversal.
    rows = conn.execute(text('''
        SELECT rtl.id, rtl.receipt_table_id, rtl.line_index, rtl.raw_label,
               rtl.normalized_label, rtl.external_article_code, rtl.quantity,
               rtl.unit_price, rtl.line_total, rtl.line_role, rtl.inventory_eligible,
               rtl.is_deleted, rtl.matched_article_id, rtl.matched_global_product_id,
               rt.approved_at, rt.household_id
        FROM receipt_table_lines rtl JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
        ORDER BY rtl.receipt_table_id, rtl.line_index, rtl.id
    ''' + (' FOR UPDATE OF rtl, rt' if lock else ''))).mappings().all()
    plan = []
    previous = None
    for raw in rows:
        row = dict(raw)
        same_receipt = previous and previous['receipt_table_id'] == row['receipt_table_id']
        if (same_receipt and int(row['line_index']) == int(previous['line_index']) + 1
            and row['line_role'] == 'product' and row['inventory_eligible'] == 1
            and not row['is_deleted'] and not previous['is_deleted']
            and previous['line_role'] == 'product' and previous['inventory_eligible'] == 1
            and not row['approved_at']
            and not row['matched_article_id'] and not row['matched_global_product_id']
            and confirmed_weight_continuation(previous, row)):
            candidate_count = conn.execute(text('SELECT COUNT(*) FROM external_product_candidates WHERE receipt_line_id=:id'), {'id':row['id']}).scalar_one()
            if candidate_count == 0:
                plan.append({
                    'id':row['id'], 'receipt_table_id':row['receipt_table_id'],
                    'household_id':row['household_id'], 'parent_product_line_id':previous['id'],
                    'raw_label':row['raw_label'], 'normalized_label':row['normalized_label'],
                    'source_snapshot': row, 'parent_product_snapshot': previous,
                    'before':{'is_deleted':row['is_deleted'],'line_role':row['line_role'],
                              'inventory_eligible':row['inventory_eligible']},
                })
        previous = row
    return plan


def apply_plan(conn, expected_digest):
    plan = build_plan(conn, lock=True)
    if plan_digest(plan) != expected_digest:
        raise ValueError('De gegevens zijn gewijzigd sinds de veiligheidskopie. Geen herstel uitgevoerd.')
    for item in plan:
        result = conn.execute(text('''UPDATE receipt_table_lines
            SET is_deleted=TRUE, line_role='metadata', inventory_eligible=0
            WHERE id=:id AND receipt_table_id=:receipt AND line_role='product'
              AND inventory_eligible=1 AND COALESCE(is_deleted,FALSE)=FALSE
              AND EXISTS (SELECT 1 FROM receipt_tables rt WHERE rt.id=:receipt AND rt.household_id=:household AND rt.approved_at IS NULL)
        '''), {'id':item['id'],'receipt':item['receipt_table_id'],'household':item['household_id']})
        if result.rowcount != 1:
            raise ValueError('Regel gewijzigd tijdens herstel; gehele transactie terugdraaien.')
    return len(plan)
