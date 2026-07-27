from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_ROUTES = ROOT / "backend" / "app" / "api" / "system_routes.py"
RECEIPT_OVERVIEW = ROOT / "frontend" / "src" / "features" / "externalDatabases" / "ReceiptItemsOverview.jsx"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-receipt-pagination-integration.yml"
SELF = Path(__file__).resolve()


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 anker, gevonden {count}")
    return source.replace(old, new, 1)


routes = SYSTEM_ROUTES.read_text(encoding="utf-8")
routes = replace_once(
    routes,
    "from app.services.external_receipt_item_read_service import (\n    list_external_receipt_items_read_only,\n    repair_confirmed_external_catalog_links,\n)",
    "from app.services.external_receipt_item_read_service import (\n    list_external_receipt_items_page_read_only,\n    list_external_receipt_items_read_only,\n    repair_confirmed_external_catalog_links,\n)",
    label="backendimport",
)
routes = replace_once(
    routes,
    """@router.get('/api/external-databases/receipt-items')
def external_databases_receipt_items(limit: int = Query(default=200)):
    payload = list_external_receipt_items_read_only(limit=limit)
    payload = _without_taxonomy_seed_candidates(payload)
    return _without_spaarzegels_receipt_items(payload)
""",
    """@router.get('/api/external-databases/receipt-items')
def external_databases_receipt_items(
    limit: int = Query(default=200),
    page: int | None = Query(default=None),
    page_size: int = Query(default=10),
    sort_key: str = Query(default='receiptLineText'),
    sort_desc: bool = Query(default=False),
    receiptLineText: str = Query(default=''),
    retailerCode: str = Query(default=''),
    catalogLinked: str = Query(default='all'),
    quantity: str = Query(default=''),
    price: str = Query(default=''),
    bestCandidateName: str = Query(default=''),
    productType: str = Query(default=''),
    bestCandidateCode: str = Query(default=''),
    bestCandidateScore: str = Query(default=''),
    candidateCount: str = Query(default=''),
):
    if page is None:
        payload = list_external_receipt_items_read_only(limit=limit)
    else:
        payload = list_external_receipt_items_page_read_only(
            page=page,
            page_size=page_size,
            sort_key=sort_key,
            sort_desc=sort_desc,
            filters={
                'receiptLineText': receiptLineText,
                'retailerCode': retailerCode,
                'catalogLinked': catalogLinked,
                'quantity': quantity,
                'price': price,
                'bestCandidateName': bestCandidateName,
                'productType': productType,
                'bestCandidateCode': bestCandidateCode,
                'bestCandidateScore': bestCandidateScore,
                'candidateCount': candidateCount,
            },
        )
    payload = _without_taxonomy_seed_candidates(payload)
    return _without_spaarzegels_receipt_items(payload)
""",
    label="backendroute",
)
SYSTEM_ROUTES.write_text(routes, encoding="utf-8", newline="\n")

frontend = RECEIPT_OVERVIEW.read_text(encoding="utf-8")
frontend = replace_once(
    frontend,
    "import { useEffect, useMemo, useState } from 'react'",
    "import { useEffect, useState } from 'react'",
    label="reactimport",
)
frontend = replace_once(
    frontend,
    "  const [page, setPage] = useState(1)\n  const [barcodeDraft, setBarcodeDraft] = useState('')",
    "  const [page, setPage] = useState(1)\n  const [pageCount, setPageCount] = useState(1)\n  const [totalItems, setTotalItems] = useState(0)\n  const [barcodeDraft, setBarcodeDraft] = useState('')",
    label="paginastatus",
)
frontend = replace_once(
    frontend,
    """  async function fetchItems() {
    const response = await fetchJsonWithAuth('/api/external-databases/receipt-items?limit=500', { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return buildReceiptItems(Array.isArray(data?.items) ? data.items : [])
  }
""",
    """  async function fetchItems() {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PAGE_SIZE),
      sort_key: sortKey,
      sort_desc: String(sortDesc),
    })
    Object.entries(filters).forEach(([key, value]) => {
      const normalized = String(value ?? '').trim()
      if (normalized || key === 'catalogLinked') params.set(key, normalized || 'all')
    })
    const response = await fetchJsonWithAuth(`/api/external-databases/receipt-items?${params.toString()}`, { method: 'GET' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data?.detail || 'Bonartikelen konden niet worden geladen')
    return {
      items: buildReceiptItems(Array.isArray(data?.items) ? data.items : []),
      total: Number(data?.total || 0),
      pageCount: Math.max(1, Number(data?.page_count || 1)),
      page: Math.max(1, Number(data?.page || page)),
    }
  }
""",
    label="frontendfetch",
)
frontend = replace_once(
    frontend,
    """  async function loadItems() {
    try {
      const nextItems = await fetchItems()
      setItems(nextItems)
      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
    } catch (err) { onError?.(err?.message || 'Bonartikelen konden niet worden geladen') }
  }
""",
    """  async function loadItems() {
    try {
      const payload = await fetchItems()
      const nextItems = payload.items
      setItems(nextItems)
      setTotalItems(payload.total)
      setPageCount(payload.pageCount)
      if (payload.page !== page) setPage(payload.page)
      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)
      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))
    } catch (err) { onError?.(err?.message || 'Bonartikelen konden niet worden geladen') }
  }
""",
    label="frontendload",
)
old_block = """  useEffect(() => {
    loadItems()
    loadProductTypeOptions().catch((err) => onError?.(err?.message || 'Producttypen konden niet worden geladen'))
  }, [])

  const filteredItems = useMemo(() => {
    const rows = items.filter((item) => item.receiptLineText.toLowerCase().includes(filters.receiptLineText.toLowerCase()) && item.retailerCode.toLowerCase().includes(filters.retailerCode.toLowerCase()) && ((filters.catalogLinked === 'all') || (filters.catalogLinked === 'linked' && item.catalogLinked) || (filters.catalogLinked === 'unlinked' && !item.catalogLinked)) && item.quantity.toLowerCase().includes(filters.quantity.toLowerCase()) && numberText(item.price).toLowerCase().includes(filters.price.toLowerCase()) && String(item.bestCandidateName || '').toLowerCase().includes(filters.bestCandidateName.toLowerCase()) && String(item.productType || '').toLowerCase().includes(filters.productType.toLowerCase()) && String(item.bestCandidateCode || '').toLowerCase().includes(filters.bestCandidateCode.toLowerCase()) && scoreText(item.bestCandidateScore).toLowerCase().includes(filters.bestCandidateScore.toLowerCase()) && String(item.candidateCount || '').toLowerCase().includes(filters.candidateCount.toLowerCase()))
    rows.sort((leftItem, rightItem) => { const left = String(leftItem[sortKey] ?? '').toLowerCase(); const right = String(rightItem[sortKey] ?? '').toLowerCase(); if (left < right) return sortDesc ? 1 : -1; if (left > right) return sortDesc ? -1 : 1; return 0 })
    return rows
  }, [items, filters, sortKey, sortDesc])

  useEffect(() => {
    if (!selectedItem) return
    if (filteredItems.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null); setSelectedCandidateId(''); setOffPreview(null); setOffSearchResults([]); setOffError(''); setOffSearchText(''); setOffSearchMode('automatisch'); setProductTypeMode('existing'); setSelectedProductTypeId(''); setNewProductTypeName('')
  }, [filteredItems, selectedItem])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visibleItems = filteredItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
"""
new_block = """  useEffect(() => {
    loadProductTypeOptions().catch((err) => onError?.(err?.message || 'Producttypen konden niet worden geladen'))
  }, [])

  useEffect(() => {
    loadItems()
  }, [page, sortKey, sortDesc, filters])

  useEffect(() => {
    if (!selectedItem) return
    if (items.some((item) => item.id === selectedItem.id)) return
    setSelectedItem(null); setSelectedCandidateId(''); setOffPreview(null); setOffSearchResults([]); setOffError(''); setOffSearchText(''); setOffSearchMode('automatisch'); setProductTypeMode('existing'); setSelectedProductTypeId(''); setNewProductTypeName('')
  }, [items, selectedItem])

  const currentPage = Math.min(page, pageCount)
  const visibleItems = items
"""
frontend = replace_once(frontend, old_block, new_block, label="frontendserverstate")
frontend = replace_once(
    frontend,
    '<span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length}</span>',
    '<span className="rz-external-databases-muted">Geselecteerd: {selectedItemIds.length} · Totaal: {totalItems}</span>',
    label="frontendtotal",
)
RECEIPT_OVERVIEW.write_text(frontend, encoding="utf-8", newline="\n")

if WORKFLOW.exists():
    WORKFLOW.unlink()
if SELF.exists():
    SELF.unlink()

print("RECEIPT_PAGINATION_INTEGRATION_APPLIED")
