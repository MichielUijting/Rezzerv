from pathlib import Path


path = Path("backend/app/main.py")
text = path.read_text(encoding="utf-8")
start_marker = "def update_household_article_details_by_id(conn, household_id: str, household_article_id: str, payload: ArticleHouseholdDetailsUpdateRequest) -> dict:\n"
end_marker = "\n\ndef update_household_article_details(conn, household_id: str, article_name: str, payload: ArticleHouseholdDetailsUpdateRequest) -> dict:\n"
start = text.find(start_marker)
if start < 0:
    raise SystemExit("Article-detail PATCH function start marker not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("Article-detail PATCH function end marker not found")
old = text[start:end]
if "provided_fields = set(getattr(payload, 'model_fields_set'" in old:
    raise SystemExit("Partial PATCH semantics already present; refusing duplicate patch")

new = '''def update_household_article_details_by_id(conn, household_id: str, household_article_id: str, payload: ArticleHouseholdDetailsUpdateRequest) -> dict:
    resolved_article_id = str(household_article_id or '').strip()
    if not resolved_article_id:
        raise HTTPException(status_code=400, detail='household_article_id is verplicht')
    article_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')

    provided_fields = set(getattr(payload, 'model_fields_set', None) or getattr(payload, '__fields_set__', set()) or set())
    unsupported_fields = provided_fields.intersection({'category', 'brand_or_maker', 'short_description'})
    if unsupported_fields:
        names = ', '.join(sorted(unsupported_fields))
        raise HTTPException(status_code=400, detail=f'Veld(en) niet muteerbaar via huishoud-artikeldetails: {names}')
    if not provided_fields:
        return get_household_article_details(conn, household_id, str(article_row.get('naam') or '').strip())

    custom_name = normalize_optional_text_field(payload.custom_name) if 'custom_name' in provided_fields else None
    article_type = normalize_optional_text_field(payload.article_type) if 'article_type' in provided_fields else None
    notes = normalize_optional_text_field(payload.notes) if 'notes' in provided_fields else None
    favorite_store = normalize_optional_text_field(payload.favorite_store) if 'favorite_store' in provided_fields else None
    min_stock = normalize_optional_numeric_field(payload.min_stock) if 'min_stock' in provided_fields else None
    ideal_stock = normalize_optional_numeric_field(payload.ideal_stock) if 'ideal_stock' in provided_fields else None
    barcode = normalize_barcode_value(payload.barcode) if 'barcode' in provided_fields and payload.barcode not in (None, '') else None
    article_number = normalize_optional_text_field(payload.article_number) if 'article_number' in provided_fields else None
    source = normalize_optional_text_field(payload.source) if 'source' in provided_fields else None
    if 'source' not in provided_fields and (
        ('barcode' in provided_fields and barcode) or ('article_number' in provided_fields and article_number)
    ):
        source = 'manual'

    effective_min_stock = min_stock if 'min_stock' in provided_fields else normalize_optional_numeric_field(article_row.get('min_stock'))
    effective_ideal_stock = ideal_stock if 'ideal_stock' in provided_fields else normalize_optional_numeric_field(article_row.get('ideal_stock'))
    if effective_min_stock is not None and effective_ideal_stock is not None and effective_min_stock > effective_ideal_stock:
        raise HTTPException(status_code=400, detail='Minimumvoorraad mag niet groter zijn dan streefvoorraad')
    if 'barcode' in provided_fields and barcode:
        existing_barcode_row = get_household_article_by_barcode(conn, household_id, barcode)
        if existing_barcode_row and str(existing_barcode_row.get('id') or '').strip() != resolved_article_id:
            raise HTTPException(status_code=409, detail='Barcode is al gekoppeld aan een ander artikel')

    column_by_field = {
        'custom_name': 'custom_name',
        'article_type': 'article_type',
        'notes': 'notes',
        'min_stock': 'min_stock',
        'ideal_stock': 'ideal_stock',
        'favorite_store': 'favorite_store',
        'barcode': 'barcode',
        'article_number': 'article_number',
        'source': 'external_source',
    }
    value_by_field = {
        'custom_name': custom_name,
        'article_type': article_type,
        'notes': notes,
        'min_stock': min_stock,
        'ideal_stock': ideal_stock,
        'favorite_store': favorite_store,
        'barcode': barcode,
        'article_number': article_number,
        'source': source,
    }
    fields_to_write = [field for field in column_by_field if field in provided_fields]
    if source == 'manual' and 'source' not in fields_to_write:
        fields_to_write.append('source')
    if fields_to_write:
        set_clause = ',\n                '.join(f"{column_by_field[field]} = :{field}" for field in fields_to_write)
        params = {field: value_by_field[field] for field in fields_to_write}
        params.update({
            'household_id': str(household_id),
            'household_article_id': resolved_article_id,
        })
        conn.execute(
            text(
                f"""
                UPDATE household_articles
                SET {set_clause},
                    updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id AND id = :household_article_id
                """
            ),
            params,
        )

    refreshed_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if refreshed_row:
        refreshed_article_id = str(refreshed_row.get('id') or '')
        if 'barcode' in provided_fields:
            if barcode:
                clear_primary_barcode_identity_for_article(conn, refreshed_article_id)
                upsert_product_identity(conn, refreshed_article_id, 'gtin', barcode, source or 'manual', confidence_score=1.0, is_primary=True)
                ensure_household_article_global_product_link(conn, refreshed_article_id, barcode)
                ensure_article_product_enrichment(conn, refreshed_article_id, barcode, force_refresh=True)
            else:
                clear_primary_barcode_identity_for_article(conn, refreshed_article_id)
                conn.execute(text(
                    """
                    UPDATE product_enrichments
                    SET lookup_status = CASE WHEN lookup_status = 'found' THEN 'skipped' ELSE lookup_status END,
                        last_lookup_message = CASE
                            WHEN COALESCE(trim(last_lookup_message), '') = '' THEN 'Barcode verwijderd; eerdere verrijking is alleen nog historisch'
                            ELSE last_lookup_message
                        END,
                        last_lookup_at = CURRENT_TIMESTAMP,
                        normalized_barcode = NULL
                    WHERE household_article_id = :household_article_id AND global_product_id IS NULL
                    """
                ), {'household_article_id': refreshed_article_id})
                ensure_household_article_global_product_link(conn, refreshed_article_id)
                if article_number:
                    write_product_enrichment_audit(conn, refreshed_article_id, source or 'manual', 'identify', 'skipped', message='Extern artikelnummer opgeslagen zonder barcode')
        elif 'article_number' in provided_fields and article_number:
            write_product_enrichment_audit(conn, refreshed_article_id, source or 'manual', 'identify', 'skipped', message='Extern artikelnummer opgeslagen zonder barcodewijziging')
    return get_household_article_details(conn, household_id, str((refreshed_row or article_row).get('naam') or '').strip())
'''

path.write_text(text[:start] + new + text[end:], encoding="utf-8")
