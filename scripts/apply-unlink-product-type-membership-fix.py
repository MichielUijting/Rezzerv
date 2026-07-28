from pathlib import Path

SERVICE = Path('backend/app/services/off_product_link_service.py')
FRONTEND = Path('frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: verwacht exact 1 bronfragment, gevonden {count}')
    return source.replace(old, new, 1)


def patch_service() -> None:
    source = SERVICE.read_text(encoding='utf-8')

    source = replace_once(
        source,
        '''    Het centrale catalogusproduct, de GTIN en de officiële GPC-classificatie
    blijven bestaan. Alleen de foutieve bon-/huishoudartikelkoppeling en de
    algemene winkelartikelkoppeling worden beëindigd. Er ontstaat geen
    voorraadmutatie.
''',
        '''    Het centrale catalogusproduct en de GTIN blijven bestaan. De foutieve
    bon-/huishoudartikelkoppeling, de algemene winkelartikelkoppeling en de
    actieve Producttypekoppeling van het universele artikel worden beëindigd.
    Historie blijft behouden en er ontstaat geen voorraadmutatie.
''',
        'service docstring',
    )

    anchor = '''        deactivated_links = deactivate_global_external_article_product_link(
            conn,
            retailer_code=identity["retailer_code"],
            receipt_text=identity["receipt_text"],
            external_article_code=identity["external_article_code"],
        )

'''
    insertion = anchor + '''        product_type_memberships_unlinked = 0
        if global_product_id and _table_exists(conn, "product_group_memberships"):
            membership_columns = _table_columns(conn, "product_group_memberships")
            if {"global_product_id", "active"}.issubset(membership_columns):
                updated_at_sql = (
                    ", updated_at = CURRENT_TIMESTAMP"
                    if "updated_at" in membership_columns
                    else ""
                )
                result = conn.execute(
                    text(
                        f"""
                        UPDATE product_group_memberships
                        SET active = 0{updated_at_sql}
                        WHERE global_product_id = :global_product_id
                          AND COALESCE(active, 1) = 1
                        """
                    ),
                    {"global_product_id": global_product_id},
                )
                product_type_memberships_unlinked = int(result.rowcount or 0)

'''
    source = replace_once(source, anchor, insertion, 'Producttype ontkoppeling')

    source = replace_once(
        source,
        '''        "catalog_product_deleted": False,
        "product_type_deleted": False,
        "inventory_mutated": False,
''',
        '''        "catalog_product_deleted": False,
        "product_type_deleted": False,
        "product_type_unlinked": product_type_memberships_unlinked > 0,
        "product_type_memberships_unlinked": product_type_memberships_unlinked,
        "inventory_mutated": False,
''',
        'service response',
    )

    required = (
        'product_type_memberships_unlinked = 0',
        'UPDATE product_group_memberships',
        'SET active = 0',
        '"product_type_unlinked": product_type_memberships_unlinked > 0',
        '"catalog_product_deleted": False',
        '"inventory_mutated": False',
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'service marker ontbreekt: {marker}')

    SERVICE.write_text(source, encoding='utf-8', newline='')


def patch_frontend() -> None:
    source = FRONTEND.read_text(encoding='utf-8')
    source = replace_once(
        source,
        "      onMessage?.('Kandidaat is ontkoppeld.'); setSelectedCandidateId(''); await loadItems()",
        "      onMessage?.(data?.product_type_unlinked ? 'Kandidaat en Producttype zijn ontkoppeld.' : 'Kandidaat is ontkoppeld; er was geen actieve Producttypekoppeling.'); setSelectedCandidateId(''); setSelectedProductTypeId(''); setProductTypeClassificationStatus(''); await Promise.all([loadItems(), loadProductTypeOptions()])",
        'frontend succesmelding',
    )

    required = (
        'Kandidaat en Producttype zijn ontkoppeld.',
        "setSelectedProductTypeId('')",
        "setProductTypeClassificationStatus('')",
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'frontend marker ontbreekt: {marker}')

    FRONTEND.write_text(source, encoding='utf-8', newline='')


def main() -> None:
    patch_service()
    patch_frontend()
    print('UNLINK_CANDIDATE_AND_PRODUCT_TYPE_FIX_APPLIED')


if __name__ == '__main__':
    main()
