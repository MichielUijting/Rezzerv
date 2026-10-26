from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.maintenance.repair_weight_detail_rows import build_plan, apply_plan, plan_digest
from app.receipt_ingestion.weight_detail import normalize_legacy_weight_details


def row(index, detail=False, **changes):
    return dict(id=str(index), receipt_table_id='receipt', line_index=index,
        raw_label='0,094 kg x 5,99 EUR' if detail else 'Gewogen artikel 0,56',
        normalized_label='Gewogen artikel', external_article_code='same-sku', quantity='0.094',
        unit_price='5.99', line_total='0.56', line_role='product', inventory_eligible=1,
        is_deleted=False, matched_article_id=None, matched_global_product_id=None,
        approved_at=None, household_id='household', **changes)


class Connection:
    def __init__(self, rows, candidates=0):
        self.rows, self.candidates, self.writes = deepcopy(rows), candidates, []

    def execute(self, statement, params=None):
        sql = str(statement).strip()
        if sql.startswith('SELECT COUNT'):
            return SimpleNamespace(scalar_one=lambda: self.candidates)
        if sql.startswith('SELECT'):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))
        assert sql.startswith('UPDATE receipt_table_lines')
        target = next(r for r in self.rows if r['id'] == params['id'])
        self.writes.append(params)
        target.update(is_deleted=True,line_role='metadata',inventory_eligible=0)
        return SimpleNamespace(rowcount=1)


def test_cleanup_removes_only_proven_duplicate_and_is_idempotent():
    conn = Connection([row(0),row(1,True)])
    plan = build_plan(conn)
    assert len(plan) == 1 and not conn.writes
    assert plan[0]['parent_product_line_id'] == '0'
    assert apply_plan(conn,plan_digest(plan)) == 1
    assert conn.rows[0]['line_role'] == 'product' and not conn.rows[0]['is_deleted']
    assert conn.rows[1]['line_role'] == 'metadata' and conn.rows[1]['inventory_eligible'] == 0
    assert build_plan(conn) == []
    assert apply_plan(conn,plan_digest([])) == 0


@pytest.mark.parametrize('field,value', [('external_article_code','different'),('quantity','0.2'),
    ('unit_price','8.99'),('matched_article_id','linked'),('matched_global_product_id','linked'),
    ('approved_at','2026-01-01'),('receipt_table_id','other-receipt'),('line_index',3)])
def test_cleanup_preserves_conflicts_linked_or_approved_data(field,value):
    detail = row(1,True)
    detail[field]=value
    assert build_plan(Connection([row(0),detail])) == []


def test_candidate_link_and_changed_backup_abort_cleanup():
    assert build_plan(Connection([row(0),row(1,True)],candidates=1)) == []
    conn=Connection([row(0),row(1,True)])
    with pytest.raises(ValueError,match='gewijzigd'):
        apply_plan(conn,'stale-backup')
    assert not conn.writes


def test_legacy_source_also_removes_proven_details_and_preserves_repeated_products():
    product, detail = row(0), row(1, True)
    normalized, review = normalize_legacy_weight_details([product, detail, product])
    assert normalized == [product, product] and not review
    detail['external_article_code'] = 'conflict'
    normalized, review = normalize_legacy_weight_details([product, detail])
    assert review and normalized[1]['line_type'] == 'unknown'
    assert normalized[0] == product and 'line_type' not in detail


def test_legacy_parser_boundary_publishes_unknown_for_unproven_detail(monkeypatch):
    from app.services import receipt_service
    parsed = SimpleNamespace(is_receipt=True, lines=[row(1,True)], parse_status='approved',
                             parser_diagnostics=None, store_name='Lidl', total_amount='0.56')
    monkeypatch.setattr(receipt_service, '_parse_receipt_content_without_financial_typing', lambda *args: parsed)
    result = receipt_service.parse_receipt_content(b'test', 'bon.txt', 'text/plain')
    assert result.parse_status == 'review_needed'
    assert result.lines[0]['line_type'] == 'unknown'
    from app.receipt_ingestion.service_parts.receipt_result_helpers import determine_final_parse_status
    assert determine_final_parse_status(result) == 'review_needed'
