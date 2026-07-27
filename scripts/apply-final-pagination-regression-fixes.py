from __future__ import annotations

from pathlib import Path

FRONTEND = Path('frontend/tests/e2e/external-databases.frontend-regression.spec.js')
BACKEND = Path('backend/tests/test_off_product_type_link_contract_selftest.py')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: verwacht exact 1 treffer, gevonden {count}')
    return source.replace(old, new, 1)


def update_frontend() -> None:
    source = FRONTEND.read_text(encoding='utf-8-sig')
    source = replace_once(
        source,
        "    await expect(receiptTable.locator('tbody tr', { hasText: 'Gekoppeld filter product' })).toBeVisible();\n",
        "    await expect(receiptTable.locator('tbody tr').filter({ hasText: /^Gekoppeld filter product(?:\\s|$)/ })).toBeVisible();\n",
        'exacte gekoppelde filterrij',
    )
    FRONTEND.write_text(source, encoding='utf-8', newline='\n')


def update_backend() -> None:
    source = BACKEND.read_text(encoding='utf-8-sig')
    source = replace_once(
        source,
        '    product_type_key = f"test.off.halfvolle.melk.{suffix}"\n',
        '',
        'verwijder lokaal testproducttype',
    )
    source = replace_once(
        source,
        '        before = {\n            "candidates": _count(conn, "external_product_candidates"),\n            "inventory": _count(conn, "inventory"),\n            "events": _count(conn, "inventory_events"),\n        }\n',
        '        before = {\n            "candidates": _count(conn, "external_product_candidates"),\n            "inventory": _count(conn, "inventory"),\n            "events": _count(conn, "inventory_events"),\n        }\n        product_type = conn.execute(text("""\n            SELECT inventory_group_key\n            FROM product_inventory_groups\n            WHERE inventory_group_key LIKE \'gpc:%\'\n              AND source LIKE \'gs1_gpc_%\'\n              AND COALESCE(active, 1) = 1\n            ORDER BY inventory_group_key\n            LIMIT 1\n        """)).mappings().first()\n        if not product_type:\n            raise RuntimeError("Geen actief officieel GS1 GPC Producttype beschikbaar voor contracttest")\n        product_type_key = str(product_type["inventory_group_key"])\n',
        'selecteer bestaand officieel GPC Producttype',
    )
    source = replace_once(
        source,
        '    assignment = {\n        "create": {\n            "inventory_group_key": product_type_key,\n            "canonical_name": "Halfvolle koemelk contracttest",\n            "base_unit": "ml",\n            "aggregation_mode": "volume",\n        },\n        "mapping_source": "contract_selftest",\n        "confidence_score": 0.99,\n    }\n',
        '    assignment = {\n        "product_type_id": product_type_key,\n        "mapping_source": "contract_selftest",\n        "confidence_score": 0.99,\n    }\n',
        'gebruik officieel GPC Producttype',
    )
    source = replace_once(
        source,
        '            product_type_assignment={\n                "create": {\n                    "inventory_group_key": f"test.rollback.{suffix}",\n                    "canonical_name": "Rollback producttype",\n                    "base_unit": "ml",\n                    "aggregation_mode": "volume",\n                },\n                "mapping_source": "contract_selftest_rollback",\n            },\n',
        '            product_type_assignment={\n                "product_type_id": product_type_key,\n                "mapping_source": "contract_selftest_rollback",\n            },\n',
        'rollback met officieel GPC Producttype',
    )
    source = replace_once(
        source,
        '            conn.execute(text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :key"), {"key": product_type_key})\n',
        '',
        'behoud officiële GPC referentie',
    )
    BACKEND.write_text(source, encoding='utf-8', newline='\n')


def main() -> None:
    update_frontend()
    update_backend()
    print('FINAL_PAGINATION_REGRESSION_FIXES_APPLIED')


if __name__ == '__main__':
    main()
