from pathlib import Path

ROOT = Path('.')
FRONTEND = ROOT / 'frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx'
SERVICE = ROOT / 'backend/app/services/off_product_link_service.py'
API = ROOT / 'backend/app/api/product_inventory_group_routes.py'


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: verwacht 1 bronfragment, gevonden {count}')
    return source.replace(old, new, 1)


def patch_frontend() -> None:
    source = FRONTEND.read_text(encoding='utf-8')

    source = replace_once(
        source,
        '  const selectedCandidateCanBeUnlinked = false\n',
        "  const selectedCandidateCanBeUnlinked = Boolean(\n"
        "    selectedItem?.catalogLinked\n"
        "    && selectedCandidate?.isLinkedToCatalog\n"
        "    && !isLinkingProductType\n"
        "  )\n",
        'frontend ontkoppelbeschikbaarheid',
    )

    old_function = """  async function unlinkSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeUnlinked) return
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/unlink', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ context_keys: [selectedItem.contextKey || selectedItem.id], candidate_ids: [selectedCandidate.raw?.id || selectedCandidate.id] }) })
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.detail || 'Kandidaat ontkoppelen is mislukt')
      onMessage?.('Kandidaat is ontkoppeld.'); setSelectedCandidateId(''); await loadItems()
    } catch (err) { onError?.(err?.message || 'Kandidaat ontkoppelen is mislukt') }
  }
"""
    new_function = """  async function unlinkSelectedCandidate() {
    if (!selectedItem || !selectedCandidate || !selectedCandidateCanBeUnlinked) return
    setIsLinkingProductType(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-products/off/unlink', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_item_id: selectedItem.receiptItemId || selectedItem.id,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaat ontkoppelen is mislukt')
      onMessage?.('Kandidaat en Producttype zijn van het bonartikel ontkoppeld.')
      setSelectedCandidateId('')
      setSelectedProductTypeId('')
      setProductTypeSearchText('')
      setProductTypeClassificationStatus('')
      await Promise.all([loadItems(), loadProductTypeOptions()])
    } catch (err) {
      onError?.(err?.message || 'Kandidaat ontkoppelen is mislukt')
    } finally {
      setIsLinkingProductType(false)
    }
  }
"""
    source = replace_once(source, old_function, new_function, 'frontend ontkoppelfunctie')

    required = (
        'selectedCandidateCanBeUnlinked = Boolean(',
        "/api/external-products/off/unlink",
        'Kandidaat en Producttype zijn van het bonartikel ontkoppeld.',
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'frontend marker ontbreekt: {marker}')

    FRONTEND.write_text(source, encoding='utf-8', newline='')


def patch_service() -> None:
    source = SERVICE.read_text(encoding='utf-8')

    source = replace_once(
        source,
        'from app.services.external_article_confirmation_service import (\n    confirm_external_article_for_receipt_item,\n)\n',
        'from app.services.external_article_confirmation_service import (\n'
        '    confirm_external_article_for_receipt_item,\n'
        '    resolve_external_article_identity,\n'
        ')\n'
        'from app.services.external_article_product_link_domain_service import (\n'
        '    deactivate_global_external_article_product_link,\n'
        ')\n',
        'service imports',
    )

    anchor = '\n\ndef link_off_product_with_product_type(\n'
    if anchor not in source:
        raise SystemExit('service invoegpunt ontbreekt')

    function = r'''


def unlink_off_product_link(*, receipt_item_id: str) -> dict[str, Any]:
    """Ontkoppel één bonartikel en het gekoppelde huishoudartikel veilig.

    Het centrale catalogusproduct, de GTIN en de officiële GPC-classificatie
    blijven bestaan. Alleen de foutieve bon-/huishoudartikelkoppeling en de
    algemene winkelartikelkoppeling worden beëindigd. Er ontstaat geen
    voorraadmutatie.
    """
    normalized = _clean_text(receipt_item_id)
    if ":" not in normalized:
        raise ValueError("receipt_item_id heeft geen geldige canonieke prefix")

    prefix, source_id = normalized.split(":", 1)
    source_id = _clean_text(source_id)
    if not source_id:
        raise ValueError("receipt_item_id bevat geen bron-ID")

    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        inventory_before = None
        if _table_exists(conn, "inventory_events"):
            inventory_before = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()

        identity = resolve_external_article_identity(conn, normalized)
        household_article_id = None
        global_product_id = None

        if prefix == "purchase-import-line":
            row = conn.execute(
                text(
                    """
                    SELECT matched_household_article_id, matched_global_product_id
                    FROM purchase_import_lines
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Purchase-importregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_household_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    """
                    UPDATE purchase_import_lines
                    SET matched_global_product_id = NULL,
                        match_status = 'unmatched',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": source_id},
            )
        elif prefix == "receipt-table-line":
            row = conn.execute(
                text(
                    """
                    SELECT matched_article_id, matched_global_product_id
                    FROM receipt_table_lines
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Bonregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    """
                    UPDATE receipt_table_lines
                    SET matched_global_product_id = NULL,
                        article_match_status = CASE
                            WHEN COALESCE(matched_article_id, '') <> '' THEN 'matched'
                            ELSE 'unmatched'
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": source_id},
            )
        elif prefix == "receipt-line" and _table_exists(conn, "receipt_lines"):
            row = conn.execute(
                text("SELECT * FROM receipt_lines WHERE id = :id LIMIT 1"),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Receiptregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    "UPDATE receipt_lines SET matched_global_product_id = NULL WHERE id = :id"
                ),
                {"id": source_id},
            )
        else:
            raise ValueError(f"Niet-ondersteund receipt_item_id-type: {prefix}")

        household_article_unlinked = False
        if household_article_id and global_product_id:
            result = conn.execute(
                text(
                    """
                    UPDATE household_articles
                    SET global_product_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                      AND global_product_id = :global_product_id
                    """
                ),
                {
                    "id": household_article_id,
                    "global_product_id": global_product_id,
                },
            )
            household_article_unlinked = int(result.rowcount or 0) > 0

        deactivated_links = deactivate_global_external_article_product_link(
            conn,
            retailer_code=identity["retailer_code"],
            receipt_text=identity["receipt_text"],
            external_article_code=identity["external_article_code"],
        )

        if _table_exists(conn, "external_product_candidates"):
            conn.execute(
                text(
                    """
                    UPDATE external_product_candidates
                    SET is_user_confirmed = 0,
                        global_product_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE context_key = :receipt_item_id
                       OR purchase_import_line_id = :source_id
                       OR receipt_line_id = :source_id
                    """
                ),
                {
                    "receipt_item_id": normalized,
                    "source_id": source_id,
                },
            )

        if _table_exists(conn, "inventory_events"):
            inventory_after = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()
            if inventory_after != inventory_before:
                raise ValueError("Ontkoppelen heeft onverwacht de voorraad gewijzigd")

    return {
        "ok": True,
        "unlinked": True,
        "receipt_item_id": normalized,
        "global_product_id": global_product_id,
        "household_article_id": household_article_id,
        "household_article_unlinked": household_article_unlinked,
        "deactivated_external_links": deactivated_links,
        "catalog_product_deleted": False,
        "product_type_deleted": False,
        "inventory_mutated": False,
        "creates_inventory_event": False,
    }
'''

    source = source.replace(anchor, function + anchor, 1)
    if 'def unlink_off_product_link' not in source:
        raise SystemExit('service ontkoppelfunctie ontbreekt')
    SERVICE.write_text(source, encoding='utf-8', newline='')


def patch_api() -> None:
    source = API.read_text(encoding='utf-8')
    source = replace_once(
        source,
        'from app.services.off_product_link_service import link_off_product_with_product_type\n',
        'from app.services.off_product_link_service import (\n'
        '    link_off_product_with_product_type,\n'
        '    unlink_off_product_link,\n'
        ')\n',
        'api import',
    )

    anchor = "\n\n@router.post('/api/admin/inventory/groups/ensure-schema')\n"
    endpoint = """

@router.post('/api/external-products/off/unlink')
def external_off_product_unlink(payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        return unlink_off_product_link(
            receipt_item_id=str(payload.get('receipt_item_id') or '').strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
"""
    if anchor not in source:
        raise SystemExit('api invoegpunt ontbreekt')
    source = source.replace(anchor, endpoint + anchor, 1)
    if "@router.post('/api/external-products/off/unlink')" not in source:
        raise SystemExit('api ontkoppelroute ontbreekt')
    API.write_text(source, encoding='utf-8', newline='')


def main() -> None:
    patch_frontend()
    patch_service()
    patch_api()
    print('EXTERNAL_PRODUCT_UNLINK_FIX_APPLIED')


if __name__ == '__main__':
    main()
