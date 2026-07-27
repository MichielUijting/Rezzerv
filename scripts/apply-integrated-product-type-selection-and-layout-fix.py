from pathlib import Path

path = Path('frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx')
source = path.read_text(encoding='utf-8')

replacements = [
    (
        "  const [productTypeClassificationStatus, setProductTypeClassificationStatus] = useState('')\n",
        "  const [productTypeClassificationStatus, setProductTypeClassificationStatus] = useState('')\n"
        "  const [productTypeSearchText, setProductTypeSearchText] = useState('')\n",
    ),
    (
        "  const hasValidProductTypeDecision = /^gpc:\\d{8}$/.test(String(selectedProductTypeId || ''))\n",
        "  const hasValidProductTypeDecision = /^gpc:\\d{8}$/.test(String(selectedProductTypeId || ''))\n"
        "  const normalizedProductTypeSearch = productTypeSearchText.trim().toLowerCase()\n"
        "  const filteredProductTypeOptions = normalizedProductTypeSearch\n"
        "    ? productTypeOptions.filter((option) => [\n"
        "        option?.display_name,\n"
        "        option?.gpc_brick_code,\n"
        "        option?.inventory_group_key,\n"
        "      ].some((value) => String(value || '').toLowerCase().includes(normalizedProductTypeSearch)))\n"
        "    : productTypeOptions\n",
    ),
    (
        "setProductTypeMode('existing'); setSelectedProductTypeId(item.catalogLinked ? item.linkedProductTypeId : ''); setNewProductTypeName(''); if (!item.hasKnownGtin)",
        "setProductTypeMode('existing'); setSelectedProductTypeId(item.catalogLinked ? item.linkedProductTypeId : ''); setProductTypeSearchText(''); setNewProductTypeName(''); if (!item.hasKnownGtin)",
    ),
    (
        "setProductTypeClassificationStatus('GPC-classificatie niet eenduidig; koppelen is geblokkeerd.')",
        "setProductTypeClassificationStatus('GPC-classificatie niet eenduidig. Zoek en selecteer hieronder handmatig het juiste Producttype, of koppel eerst alleen de kandidaat.')",
    ),
    (
        '<div className="rz-external-receipt-detail"><h3>Koppelen kandidaten in artikel-catalogus</h3><p>Universele kandidaten voor: {selectedItem.receiptLineText}</p><div className="rz-external-link-header-grid"><div className="rz-external-link-summary"><dl>',
        '<div className="rz-external-receipt-detail"><div className="rz-external-link-header-grid"><div className="rz-external-link-summary"><h3>Koppelen kandidaten in artikel-catalogus</h3><p>Universele kandidaten voor: {selectedItem.receiptLineText}</p><dl>',
    ),
    (
        '<label className="rz-input-field"><div className="rz-label">GS1 GPC Producttype</div><select className="rz-input" aria-label="Producttype" value={selectedProductTypeId} disabled><option value="">{isClassifyingProductType ? \'Producttype wordt bepaald...\' : \'GPC-classificatie ontbreekt\'}</option>{productTypeOptions.map((option) => <option key={option.inventory_group_key} value={option.inventory_group_key}>{option.display_name} — GPC {option.gpc_brick_code}</option>)}</select></label>',
        '<label className="rz-input-field"><div className="rz-label">Producttype zoeken</div><input className="rz-input" aria-label="Producttype zoeken" value={productTypeSearchText} disabled={!selectedCandidate} onChange={(event) => setProductTypeSearchText(event.target.value)} placeholder="Zoek op naam of GPC Brickcode" /></label><label className="rz-input-field"><div className="rz-label">GS1 GPC Producttype</div><select className="rz-input" aria-label="Producttype" value={selectedProductTypeId} disabled={!selectedCandidate || isClassifyingProductType} onChange={(event) => { setSelectedProductTypeId(event.target.value); if (event.target.value) setProductTypeClassificationStatus(\'Producttype handmatig geselecteerd; controleer de keuze en bevestig de koppeling.\') }}><option value="">{isClassifyingProductType ? \'Producttype wordt bepaald...\' : \'Selecteer een Producttype\'}</option>{filteredProductTypeOptions.map((option) => <option key={option.inventory_group_key} value={option.inventory_group_key}>{option.display_name} — GPC {option.gpc_brick_code}</option>)}</select></label>',
    ),
]

for old, new in replacements:
    if old not in source:
        raise SystemExit(f'Verwacht bronfragment ontbreekt:\n{old[:180]}')
    source = source.replace(old, new, 1)

path.write_text(source, encoding='utf-8')
print('INTEGRATED_PRODUCT_TYPE_SELECTION_AND_LAYOUT_FIX_APPLIED')
