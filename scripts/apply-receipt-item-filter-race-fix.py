from pathlib import Path

path = Path('frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx')
source = path.read_text(encoding='utf-8')

replacements = [
    (
        "import { useEffect, useState } from 'react'",
        "import { useEffect, useRef, useState } from 'react'",
    ),
    (
        "  const [isSavingBarcode, setIsSavingBarcode] = useState(false)\n",
        "  const [isSavingBarcode, setIsSavingBarcode] = useState(false)\n  const loadItemsRequestId = useRef(0)\n",
    ),
    (
        "    Object.entries(filters).forEach(([key, value]) => {\n      const normalized = String(value ?? '').trim()\n      if (normalized || key === 'catalogLinked') params.set(key, normalized || 'all')\n    })",
        "    const filterParamNames = {\n      receiptLineText: 'receipt_line_text',\n      retailerCode: 'retailer_code',\n      catalogLinked: 'catalog_linked',\n      quantity: 'quantity',\n      price: 'price',\n      bestCandidateName: 'best_candidate_name',\n      productType: 'product_type',\n      bestCandidateCode: 'best_candidate_code',\n      bestCandidateScore: 'best_candidate_score',\n      candidateCount: 'candidate_count',\n    }\n    Object.entries(filters).forEach(([key, value]) => {\n      const normalized = String(value ?? '').trim()\n      const parameterName = filterParamNames[key] || key\n      if (normalized || key === 'catalogLinked') params.set(parameterName, normalized || 'all')\n    })",
    ),
    (
        "  async function loadItems() {\n    try {\n      const payload = await fetchItems()\n      const nextItems = payload.items\n      setItems(nextItems)\n      setTotalItems(payload.total)\n      setPageCount(payload.pageCount)\n      if (payload.page !== page) setPage(payload.page)\n      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)\n      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))\n    } catch (err) { onError?.(err?.message || 'Bonartikelen konden niet worden geladen') }\n  }",
        "  async function loadItems() {\n    const requestId = ++loadItemsRequestId.current\n    try {\n      const payload = await fetchItems()\n      if (requestId !== loadItemsRequestId.current) return\n      const nextItems = payload.items\n      setItems(nextItems)\n      setTotalItems(payload.total)\n      setPageCount(payload.pageCount)\n      if (payload.page !== page) setPage(payload.page)\n      setSelectedItem((current) => current ? nextItems.find((item) => item.id === current.id) || null : null)\n      setSelectedItemIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)))\n    } catch (err) {\n      if (requestId === loadItemsRequestId.current) onError?.(err?.message || 'Bonartikelen konden niet worden geladen')\n    }\n  }",
    ),
]

for old, new in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'Verwachte bronpassage niet exact eenmaal gevonden: {old[:80]!r}; aantal={count}')
    source = source.replace(old, new, 1)

required = [
    "receipt_line_text",
    "catalog_linked",
    "const requestId = ++loadItemsRequestId.current",
    "if (requestId !== loadItemsRequestId.current) return",
]
for marker in required:
    if marker not in source:
        raise SystemExit(f'Verplichte herstelmarkering ontbreekt: {marker}')

path.write_text(source, encoding='utf-8', newline='')
print('RECEIPT_ITEM_FILTER_AND_RACE_FIX_APPLIED')
