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
  { key: 'gpc_status', label: 'GS1 GPC', width: 230, sortable: true, filterable: true,
    getSortValue: (item) => item.gpc_code || 'Niet geclassificeerd',
    getFilterValue: (item) => item.gpc_code || 'Niet geclassificeerd',
    renderCell: (item) => item.gpc_code || 'Niet geclassificeerd' },
  { key: 'cbs_status', label: 'CBS ECOICOPv2', width: 260, sortable: true, filterable: true,
    getSortValue: (item) => item.cbs_code || 'Niet geclassificeerd',
    getFilterValue: (item) => item.cbs_code
      ? item.cbs_code + ' ' + item.cbs_name : 'Niet geclassificeerd',
    renderCell: (item) => item.cbs_code
      ? item.cbs_code + ' · ' + item.cbs_name : 'Niet geclassificeerd' },
]

export default function CombinedClassificationWorkspace() {
  const [products, setProducts] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [taskCount, setTaskCount] = useState(null)
  const [productTotal, setProductTotal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const mayUpdateGpc = canCurrentUserPerform('gpc.update', readStoredAuthContext())
  const selected = useMemo(() => products.find((item) => item.id === selectedId) || null, [products, selectedId])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      setTaskCount(null)
      setProductTotal(null)
      try {
        const items = []
        let total = 0
        do {
          const response = await fetchJsonWithAuth(
            `/api/cbs-classifications/workqueue?limit=${PAGE_SIZE}&offset=${items.length}`,
            { signal: controller.signal },
          )
          const data = await response.json().catch(() => ({}))
          if (!response.ok || !Array.isArray(data.items)) throw new Error('Catalogusartikelen konden niet worden geladen.')
          if (!items.length) {
            total = Number(data.total)
            setProductTotal(total)
          }
          if (data.task_count_scope !== 'page' || !Array.isArray(data.tasks)) {
            throw new Error('De unieke classificatiewerkvoorraad is niet beschikbaar.')
          }
          // Tasks are unique by canonical product ID plus official system.
          if (new Set(data.tasks.map((task) => task.key)).size !== data.tasks.length) {
            throw new Error('De werkvoorraad bevat dubbele classificatietaken.')
          }
          setTaskCount((previous) => (previous ?? 0) + data.tasks.length)
          if (!Number.isSafeInteger(total) || total < 0 || Number(data.total) !== total ||
              (!data.items.length && total > items.length)) {
            throw new Error('De artikellijst is tijdens het ophalen veranderd. Open Classificeren opnieuw.')
          }
          const currentIds = new Set(items.map((item) => item.id))
          const incomingIds = data.items.map((item) => item.id)
          if (incomingIds.some((id) => !id || currentIds.has(id)) ||
              new Set(incomingIds).size !== incomingIds.length) {
            throw new Error('De werkvoorraad bevat dubbele of ongeldige Catalogusidentiteiten.')
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
  }, [revision])

  return <section aria-label="GS1 en CBS classificeren" data-testid="combined-classification-workspace">
    <h3>Artikel classificeren</h3>
    <p>Kies één centraal Catalogusartikel; de status voor GS1 en CBS hoort bij dezelfde productidentiteit. Een keuze opent de bestaande officiële bevestigingsroutes.</p>
    {!loading && !error && productTotal !== null && taskCount !== null
      ? <p role="status" data-testid="classification-workqueue-counts">
        {productTotal} unieke Catalogusartikelen · {taskCount} open classificatietaken
        (afzonderlijk geteld voor GS1 en CBS).
      </p> : null}
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
    {selected ? <div className="rz-classification-detail" data-testid="combined-selected-article">
      <div className="rz-classification-selected-heading">
        <strong>{selected.name}{selected.brand ? ' · ' + selected.brand : ''}</strong>
        <span>Barcode: {selected.gtin || 'Niet vastgelegd'}</span>
      </div>
      <div className="rz-classification-dual-grid" data-testid="classification-dual-panels">
        <div className="rz-classification-dual-panel" aria-label="GS1 GPC-classificatie" data-testid="classification-gs1-panel">
          {!mayUpdateGpc ? <p role="status">GS1 alleen lezen: onvoldoende wijzigingsrechten.</p> : null}
          <CatalogGpcActionPage key={selected.id} embedded readOnly={!mayUpdateGpc}
            onSaved={() => setRevision((value) => value + 1)}
            selectedProduct={{ id: selected.id, name: selected.name, brand: selected.brand,
              primary_gtin: selected.gtin }} />
        </div>
        <div className="rz-classification-dual-panel" aria-label="CBS ECOICOPv2-classificatie" data-testid="classification-cbs-panel">
          <CbsClassificationPage key={selected.id + '-cbs'} embedded productId={selected.id}
            onSaved={() => setRevision((value) => value + 1)} />
        </div>
      </div>
    </div> : <p role="status">Selecteer een artikel in de tabel om beide classificaties naast elkaar te bekijken.</p>}
  </section>
}
