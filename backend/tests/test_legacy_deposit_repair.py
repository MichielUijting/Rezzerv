from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.maintenance.repair_legacy_deposit_rows import build_plan, apply_plan, build_purchase_plan, apply_purchase_plan
from app.maintenance.repair_weight_detail_rows import plan_digest


def deposit(**changes):
    data = dict(id='deposit', receipt_table_id='receipt', household_id='household',
                raw_label='Statiegeld 0,15', normalized_label='Statiegeld', line_total='0.15',
                unit_price='0.15', quantity='1', line_role='product', inventory_eligible=1,
                is_deleted=False, matched_article_id='preserved-link',
                matched_global_product_id=None, approved_at='2026-01-01')
    return {**data, **changes}


class Connection:
    def __init__(self, rows):
        self.rows, self.writes = deepcopy(rows), []

    def execute(self, statement, params=None):
        if str(statement).strip().startswith('SELECT'):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))
        row = next(row for row in self.rows if row['id'] == params['id'])
        self.writes.append(params)
        row.update(line_role='financial', inventory_eligible=0)
        return SimpleNamespace(rowcount=1)


def test_old_approved_deposit_is_reclassified_without_deleting_amount_or_links():
    conn = Connection([deposit()])
    before = deepcopy(conn.rows[0])
    plan = build_plan(conn)
    assert not conn.writes and len(plan) == 1
    assert apply_plan(conn, plan_digest(plan)) == 1
    assert conn.rows[0] == {**before, 'line_role': 'financial', 'inventory_eligible': 0}
    assert apply_plan(conn, plan_digest([])) == 0


@pytest.mark.parametrize('changes', [
    {'raw_label':'Statiegeldvrije fles', 'normalized_label':'Statiegeldvrije fles'},
    {'normalized_label':'Melk'}, {'line_total':None}, {'is_deleted':True},
    {'line_role':'financial', 'inventory_eligible':0},
])
def test_real_products_conflicts_and_already_correct_data_are_preserved(changes):
    assert build_plan(Connection([deposit(**changes)])) == []


def test_changed_source_evidence_invalidates_backup():
    conn = Connection([deposit()])
    expected = plan_digest(build_plan(conn))
    conn.rows[0]['line_total'] = '0.30'
    with pytest.raises(ValueError, match='gewijzigd'):
        apply_plan(conn, expected)
    assert not conn.writes


def test_unprocessed_standalone_import_deposit_is_backed_up_and_removed_not_real_product():
    rows = [dict(id='deposit', batch_id='batch', household_id='household',
                 article_name_raw='Statiegeld', line_price_raw='0.15', batch_source_snapshot='source'),
            dict(id='milk', batch_id='batch', household_id='household',
                 article_name_raw='Melk', line_price_raw='1.20', batch_source_snapshot='source')]
    writes = []
    def execute(statement, params=None):
        if str(statement).strip().startswith('SELECT'):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
        writes.append(params['id'])
        rows[:] = [row for row in rows if row['id'] != params['id']]
        return SimpleNamespace(rowcount=1)
    conn = SimpleNamespace(execute=execute)
    plan = build_purchase_plan(conn)
    assert len(plan) == 1 and plan[0]['source_snapshot']['batch_source_snapshot'] == 'source'
    assert apply_purchase_plan(conn, plan_digest(plan)) == 1
    assert writes == ['deposit'] and rows[0]['id'] == 'milk'
    assert apply_purchase_plan(conn, plan_digest([])) == 0
