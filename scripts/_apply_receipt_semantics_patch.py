from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return (ROOT / path).read_text(encoding='utf-8')


def save(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'PATCH FAILED: {label}')
    return text.replace(old, new, 1)

# 1. Extend the single generic classifier vocabulary; no store-specific rule.
p = 'backend/app/receipt_ingestion/line_classifier.py'
s = load(p)
s = replace_once(
    s,
    "    'lidl plus korting', 'totaal korting', 'coupon', 'voucher', 'gratis',\n)",
    "    'lidl plus korting', 'totaal korting', 'coupon', 'voucher', 'gratis',\n    'in prijs verlaagd', 'prijs verlaagd', 'prijsverlaging', 'afgeprijsd',\n    'reduced price', 'price reduction',\n)",
    'generic discount vocabulary',
)
# Remove the first PR's downstream text-based inventory gate; semantics replaces it.
s, count = re.subn(
    r"\nNON_INVENTORY_PRODUCT_RULES = frozenset\(\{.*?\n\ndef receipt_line_is_inventory_eligible\(.*?\n\n(?=def classification_allows_append)",
    "\n",
    s,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit('PATCH FAILED: remove old inventory eligibility gate')
save(p, s)

# 2. Add the authoritative semantic layer.
semantics = '''"""Persistent semantic contract for logical receipt lines.

A receipt line is classified once at ingestion and that classification is stored
on receipt_table_lines. Downstream flows consume the stored decision instead of
reclassifying a display/raw string.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import text

from app.receipt_ingestion.line_classifier import trace_receipt_text_line_classification
from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded

ROLE_PRODUCT = 'product'
ROLE_LOYALTY = 'loyalty'
ROLE_FINANCIAL = 'financial'
ROLE_METADATA = 'metadata'


def ensure_receipt_line_semantics_schema(conn) -> None:
    """Idempotently add the two active semantic columns to receipt_table_lines."""
    try:
        columns = {
            str(row.get('name') or '')
            for row in conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings().all()
        }
    except Exception:
        columns = set()
    if not columns:
        return
    if 'line_role' not in columns:
        conn.execute(text('ALTER TABLE receipt_table_lines ADD COLUMN line_role TEXT'))
    if 'inventory_eligible' not in columns:
        conn.execute(text('ALTER TABLE receipt_table_lines ADD COLUMN inventory_eligible INTEGER'))


def _semantic_text(line: dict[str, Any]) -> str:
    return str(
        line.get('corrected_raw_label')
        or line.get('normalized_label')
        or line.get('raw_label')
        or ''
    ).strip()


def _classification_trace(line: dict[str, Any], *, store_name: str | None = None) -> dict[str, Any]:
    producer = line.get('producer_trace')
    if isinstance(producer, dict):
        nested = producer.get('classification_trace')
        if isinstance(nested, dict) and nested.get('classification'):
            return dict(nested)
        if producer.get('classification'):
            return {
                'classification': producer.get('classification'),
                'rule': producer.get('classification_rule'),
                'matched': producer.get('classification_matched'),
                'stage': producer.get('classification_stage') or 'producer_trace',
            }
    label = _semantic_text(line)
    if not label:
        return {'classification': 'ignore', 'rule': 'EMPTY_OR_WHITESPACE_LINE', 'stage': 'semantic'}
    return trace_receipt_text_line_classification(label, store_name=store_name)


def derive_receipt_line_semantics(
    line: dict[str, Any],
    *,
    store_name: str | None = None,
) -> dict[str, Any]:
    """Return the persistent semantic role and inventory eligibility for one logical line."""
    if not isinstance(line, dict):
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}

    # Persisted semantics are authoritative once present.
    persisted_role = str(line.get('line_role') or '').strip()
    persisted_eligible = line.get('inventory_eligible')
    if persisted_role and persisted_eligible is not None:
        return {
            'line_role': persisted_role,
            'inventory_eligible': bool(int(persisted_eligible)) if isinstance(persisted_eligible, (int, str)) else bool(persisted_eligible),
        }

    semantic_context = dict(line)
    semantic_context.setdefault('receipt_line_text', _semantic_text(line))
    if is_spaarzegels_flow_excluded(semantic_context):
        return {'line_role': ROLE_LOYALTY, 'inventory_eligible': False}

    trace = _classification_trace(line, store_name=store_name)
    classification = str(trace.get('classification') or '')
    rule = str(trace.get('rule') or '')

    if classification == 'product_candidate':
        # Savings/action value rows may deliberately pass the product-candidate
        # gateway for financial accounting, but never become physical stock.
        if rule in {
            'GENERIC_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
            'PLUS_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
            'GENERIC_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
            'STORE_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
        }:
            return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
        return {'line_role': ROLE_PRODUCT, 'inventory_eligible': True}

    if classification in {'footer_payment_tax', 'ignore'}:
        return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
    return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
'''
save('backend/app/receipt_ingestion/receipt_line_semantics.py', semantics)

# 3. Persist semantics at both receipt-table insertion paths.
p = 'backend/app/services/receipt_service.py'
s = load(p)
s = replace_once(
    s,
    "from app.receipt_ingestion.line_classifier import classify_receipt_text_line\n",
    "from app.receipt_ingestion.line_classifier import classify_receipt_text_line\nfrom app.receipt_ingestion.receipt_line_semantics import (\n    ensure_receipt_line_semantics_schema,\n    derive_receipt_line_semantics,\n)\n",
    'receipt service semantics import',
)
# Insert ensure+derive before both parse_result loops.
needle = "            for index, line in enumerate(parse_result.lines):\n                conn.execute("
replacement = "            ensure_receipt_line_semantics_schema(conn)\n            for index, line in enumerate(parse_result.lines):\n                semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)\n                conn.execute("
if s.count(needle) < 2:
    raise SystemExit(f'PATCH FAILED: expected two parse_result loops, found {s.count(needle)}')
s = s.replace(needle, replacement)
# Add semantic columns/values to both insert variants.
s = s.replace(
    "confidence_score, logical_line_key, is_validated\n                            ) VALUES (\n                                :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score, :logical_line_key, :is_validated",
    "confidence_score, logical_line_key, is_validated, line_role, inventory_eligible\n                            ) VALUES (\n                                :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score, :logical_line_key, :is_validated, :line_role, :inventory_eligible",
)
s = s.replace(
    "confidence_score\n                        ) VALUES (\n                            :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score",
    "confidence_score, line_role, inventory_eligible\n                        ) VALUES (\n                            :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score, :line_role, :inventory_eligible",
)
# Add params after confidence_score in the two parse_result persistence blocks.
# Do this only when line[...] persistence mapping is nearby.
s = s.replace(
    "'confidence_score': line.get('confidence_score'),\n                            'logical_line_key': logical_line_key,",
    "'confidence_score': line.get('confidence_score'),\n                            'logical_line_key': logical_line_key,\n                            'line_role': semantics['line_role'],\n                            'inventory_eligible': 1 if semantics['inventory_eligible'] else 0,",
)
s = s.replace(
    "'confidence_score': line.get('confidence_score'),\n                        },\n                    )\n                )",
    "'confidence_score': line.get('confidence_score'),\n                            'line_role': semantics['line_role'],\n                            'inventory_eligible': 1 if semantics['inventory_eligible'] else 0,\n                        },\n                    )\n                )",
)
save(p, s)

# 4. Make Kassa -> Uitpakken consume persisted semantics, with one-time backfill for legacy rows.
p = 'backend/app/main.py'
s = load(p)
s = replace_once(
    s,
    "from app.receipt_ingestion.line_classifier import receipt_line_is_inventory_eligible\n",
    "from app.receipt_ingestion.receipt_line_semantics import (\n    ensure_receipt_line_semantics_schema,\n    derive_receipt_line_semantics,\n)\n",
    'main semantics import',
)
s = replace_once(
    s,
    "    existing_refs = {\n",
    "    ensure_receipt_line_semantics_schema(conn)\n\n    existing_refs = {\n",
    'ensure semantics schema in sync',
)
s = replace_once(
    s,
    "        SELECT id, line_index, logical_line_key,\n               COALESCE(corrected_raw_label, raw_label) AS raw_label,\n               COALESCE(corrected_quantity, quantity) AS quantity,\n               COALESCE(corrected_unit, unit) AS unit,\n               COALESCE(corrected_line_total, line_total) AS line_total,\n               barcode,\n",
    "        SELECT id, line_index, logical_line_key,\n               COALESCE(corrected_raw_label, raw_label) AS raw_label,\n               normalized_label,\n               COALESCE(corrected_quantity, quantity) AS quantity,\n               COALESCE(corrected_unit, unit) AS unit,\n               COALESCE(corrected_unit_price, unit_price) AS unit_price,\n               COALESCE(corrected_line_total, line_total) AS line_total,\n               discount_amount, line_role, inventory_eligible,\n               barcode,\n",
    'sync semantic columns query',
)
old = """        inventory_eligible = receipt_line_is_inventory_eligible(
            dict(line),
            store_name=str((receipt or {}).get('store_name') or '').strip() or None,
        )
        if not inventory_eligible:
"""
new = """        semantics = derive_receipt_line_semantics(
            dict(line),
            store_name=str((receipt or {}).get('store_name') or '').strip() or None,
        )
        if line.get('line_role') in (None, '') or line.get('inventory_eligible') is None:
            conn.execute(
                text(
                    "UPDATE receipt_table_lines SET line_role = :line_role, "
                    "inventory_eligible = :inventory_eligible, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                ),
                {
                    'id': line.get('id'),
                    'line_role': semantics['line_role'],
                    'inventory_eligible': 1 if semantics['inventory_eligible'] else 0,
                },
            )
        if not semantics['inventory_eligible']:
"""
s = replace_once(s, old, new, 'sync persistent semantic gate')
save(p, s)

# 5. Update contract test to require persistent semantics rather than the deleted text gate.
p = 'backend/app/testing/unpack_copies_kassa_contract.py'
s = load(p)
s = s.replace(
    '"receipt_line_is_inventory_eligible(" in sync_block',
    '"derive_receipt_line_semantics(" in sync_block and "line_role" in sync_block and "inventory_eligible" in sync_block',
)
s = s.replace(
    '"Uitpakken mist de centrale voorraadgeschiktheidsgate"',
    '"Uitpakken mist het persistente receipt-line semantiekcontract"',
)
save(p, s)

# 6. Replace first-pass unit tests with semantic-contract tests.
tests = '''from sqlalchemy import create_engine, text

from app.receipt_ingestion.receipt_line_semantics import (
    derive_receipt_line_semantics,
    ensure_receipt_line_semantics_schema,
)


def test_unknown_physical_article_is_inventory_product():
    result = derive_receipt_line_semantics({'raw_label': 'Onbekend fysiek artikel'})
    assert result == {'line_role': 'product', 'inventory_eligible': True}


def test_split_loyalty_line_uses_semantic_label_not_detail_text():
    result = derive_receipt_line_semantics({
        'raw_label': '51 x 0,10 5,10',
        'normalized_label': 'Koopzegel Digital',
        'quantity': 51,
        'unit_price': 0.10,
        'line_total': 5.10,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_producer_trace_loyalty_is_authoritative_even_when_text_has_no_keyword():
    result = derive_receipt_line_semantics({
        'raw_label': '51 x 0,10 5,10',
        'producer_trace': {
            'line_type': 'spaarzegels',
            'is_spaarzegels': True,
            'exclude_from_inventory': True,
            'external_matching_allowed': False,
        },
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_generic_discount_wording_is_financial_not_inventory():
    for label in ('In prijs verlaagd', 'Prijsverlaging', 'Afgeprijsd', 'Reduced price'):
        result = derive_receipt_line_semantics({'normalized_label': label, 'line_total': -0.20})
        assert result['line_role'] == 'financial', label
        assert result['inventory_eligible'] is False, label


def test_generic_non_inventory_charges_are_financial():
    for label in ('Statiegeld 0,25', 'Emballage 0,50', 'Verzendkosten 4,95', 'Delivery fee 3,50'):
        result = derive_receipt_line_semantics({'normalized_label': label})
        assert result['inventory_eligible'] is False, label


def test_persisted_semantics_are_not_reclassified_downstream():
    result = derive_receipt_line_semantics({
        'raw_label': 'arbitrary display text',
        'line_role': 'loyalty',
        'inventory_eligible': 0,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_schema_columns_are_active_and_idempotent():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE receipt_table_lines (id TEXT PRIMARY KEY, raw_label TEXT)'))
        ensure_receipt_line_semantics_schema(conn)
        ensure_receipt_line_semantics_schema(conn)
        columns = {row['name'] for row in conn.execute(text('PRAGMA table_info(receipt_table_lines)')).mappings()}
    assert {'line_role', 'inventory_eligible'} <= columns
'''
save('backend/tests/test_receipt_inventory_eligibility.py', tests)

print('PATCH_APPLIED_OK')
