from pathlib import Path

path = Path('backend/app/services/product_type_household_settings_service.py')
text = path.read_text(encoding='utf-8')

old = '''    grouped: dict[str, dict[str, Any]] = {}
    unmapped: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        product_type_id = _clean(row.get("product_type_id"))
        source = {
            "household_article_id": row.get("household_article_id"),
            "household_article_name": row.get("household_article_name"),
            "global_product_id": row.get("global_product_id"),
            **{field: row.get(field) for field in MIGRATABLE_FIELDS},
        }
        if not product_type_id:
            unmapped.append(source)
            continue
        bucket = grouped.setdefault(product_type_id, {
            "product_type_id": product_type_id,
            "product_type_name": row.get("product_type_name"),
            "base_unit": row.get("base_unit"),
            "source_articles": [],
        })
        bucket["source_articles"].append(source)
'''

new = '''    grouped: dict[str, dict[str, Any]] = {}
    unmapped: list[dict[str, Any]] = []
    unmapped_article_ids: set[str] = set()
    for raw in rows:
        row = dict(raw)
        product_type_id = _clean(row.get("product_type_id"))
        source = {
            "household_article_id": row.get("household_article_id"),
            "household_article_name": row.get("household_article_name"),
            "global_product_id": row.get("global_product_id"),
            **{field: row.get(field) for field in MIGRATABLE_FIELDS},
        }
        source_article_id = _clean(source.get("household_article_id"))
        if not product_type_id:
            if not source_article_id or source_article_id not in unmapped_article_ids:
                unmapped.append(source)
                if source_article_id:
                    unmapped_article_ids.add(source_article_id)
            continue
        bucket = grouped.setdefault(product_type_id, {
            "product_type_id": product_type_id,
            "product_type_name": row.get("product_type_name"),
            "base_unit": row.get("base_unit"),
            "source_articles": [],
        })
        already_present = any(
            _clean(existing.get("household_article_id")) == source_article_id
            for existing in bucket["source_articles"]
        ) if source_article_id else False
        if not already_present:
            bucket["source_articles"].append(source)
'''

count = text.count(old)
if count != 1:
    raise SystemExit(f'Verwacht exact 1 migratieblok, gevonden: {count}')

text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('PRODUCT_TYPE_MIGRATION_DEDUP_FIX_APPLIED')
