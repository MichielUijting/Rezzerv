import { useEffect, useMemo, useState } from 'react'
import CatalogGpcActionPage from '../catalog/CatalogGpcActionPage'
import CbsClassificationPage from '../catalog/CbsClassificationPage'
import DataTable from '../../ui/DataTable'
import { fetchJsonWithAuth, canCurrentUserPerform, readStoredAuthContext } from '../../lib/authSession'

const PAGE_SIZE = 100

const columns = [
  { key: 'name', label: 'Artikel', width: 280, sortable: true, filterable: true,
    renderCell: (item) => item.name + (item.brand ? ' · ' + item.brand : '') },
  { key: 'gtin', label: 'Barcode', width: 160, sortable: true, filterable: true },
  { key: 'cbs_status', label: 'CBS', width: 260, sortable: true, filterable: true,
    getSortValue: (item) => item.classified ? item.category_name : 'Niet geclassificeerd',
    getFilterValue: (item) => item.classified ? item.cbs_code + ' ' + item.category_name : 'Niet geclassificeerd',
    renderCell: (item) => item.classified
      ? item.cbs_code + ' · ' + item.category_name : 'Niet geclassificeerd' },
]

export default function CombinedClassificationWorkspace() {
  const [products, setProducts] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const mayUpdateGpc = canCurrentUserPerform('gpc.update', readStoredAuthContext())
  const selected = useMemo(() => products.find((item) => item.id === selectedId) || null, [products, selectedId])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const items = []
        let total = 0
        do {
          const response = await fetchJsonWithAuth(
            `/api/cbs-classifications/products?limit=${PAGE_SIZE}&offset=${items.length}`,
            { signal: controller.signal },
          )
          const data = await response.json().catch(() => ({}))
          if (!response.ok || !Array.isArray(data.items)) throw new Error('Catalogusartikelen konden niet worden geladen.')
          if (!items.length) total = Number(data.total)
          if (!Number.isSafeInteger(total) || total < 0 || Number(data.total) !== total ||
              (!data.items.length && total > items.length)) {
            throw new Error('De artikellijst is tijdens het ophalen veranderd. Open Classificeren opnieuw.')
          }
          items.push(...data.items)
        } while (items.length < total)
        if (!controller.signal.aborted) setProducts(items)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message || 'Artikelen niet beschikbaar.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [])

  return <section aria-label="GS1 en CBS classificeren" data-testid="combined-classification-workspace">
    <h3>Artikel classificeren</h3>
    <p>Kies hieronder één centraal Catalogusartikel. Daarna verschijnen de GS1 GPC- en CBS ECOICOPv2-classificaties voor hetzelfde artikel.</p>
    {error ? <p role="alert">{error}</p> : null}
    <DataTable
      dataTestId="combined-classification-articles"
      columns={columns} data={products}
      getRowKey={(item) => item.id}
      pageSize={8}
      emptyMessage={loading ? 'Catalogusartikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen Catalogusartikelen.'}
      renderRow={(item) => <tr key={item.id} tabIndex={0}
        aria-selected={selectedId === item.id}
        className={selectedId === item.id ? 'rz-row-selected' : ''}
        onClick={() => setSelectedId(item.id)}
        onDoubleClick={() => setSelectedId(item.id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setSelectedId(item.id)
          }
        }}>
        {columns.map((column) => <td key={column.key}>
          {typeof column.renderCell === 'function' ? column.renderCell(item) : item[column.key]}
        </td>)}
      </tr>}
    />
    {selected ? <div data-testid="combined-selected-article">
      <h3>{selected.name}{selected.brand ? ' · ' + selected.brand : ''}</h3>
      <p>Barcode: {selected.gtin || 'Niet vastgelegd'}</p>
      {!mayUpdateGpc ? <p role="status">GS1 is alleen-lezen: je hebt geen bevoegdheid om GS1 te wijzigen.</p> : null}
      <CatalogGpcActionPage key={selected.id} embedded readOnly={!mayUpdateGpc}
        selectedProduct={{ id: selected.id, name: selected.name, brand: selected.brand,
          primary_gtin: selected.gtin }} />
      <CbsClassificationPage key={selected.id + '-cbs'} embedded productId={selected.id} />
    </div> : <p role="status">Selecteer een artikel in de tabel om zowel GS1 als CBS te bekijken en te wijzigen.</p>}
  </section>
}
