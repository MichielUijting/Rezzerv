import { useEffect, useMemo, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { projectArticleWorkQueue, WORK_TYPES } from './articleManagementWorkQueueModel'

const PAGE_SIZE = 100
const RETAILERS = {
  ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', lidl: 'Lidl',
  jumbo: 'Jumbo', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic',
}
const LABELS = Object.fromEntries(WORK_TYPES.map(({ key, title }) => [key, title]))
const columns = [
  { key: 'name', label: 'Artikel', width: 250, sortable: true, filterable: true },
  { key: 'retailerLabel', label: 'Winkelketen', width: 135, sortable: true, filterable: true },
  { key: 'number', label: 'Bonartikelnummer', width: 155, sortable: true, filterable: true },
  { key: 'barcode', label: 'Art./Barcode', width: 145, sortable: true, filterable: true },
  { key: 'typeLabel', label: 'Taak', width: 180, sortable: true, filterable: true },
  { key: 'reason', label: 'Waarom deze taak?', width: 360, sortable: true, filterable: true },
]

async function readFullClassificationWorkQueue(signal) {
  const products = []
  const tasks = []
  let total = null
  const seenProductIds = new Set()
  const seenTaskKeys = new Set()
  do {
    const response = await fetchJsonWithAuth(
      '/api/cbs-classifications/workqueue?limit=' + PAGE_SIZE + '&offset=' + products.length,
      { method: 'GET', signal },
    )
    if (!response.ok) throw new Error('De classificatietaken konden niet worden opgehaald.')
    const data = await response.json().catch(() => ({}))
    if (!Array.isArray(data.items) || !Array.isArray(data.tasks)
        || data.task_count_scope !== 'page' || data.product_count_scope !== 'global'
        || !Number.isSafeInteger(data.total) || data.total < 0
        || (total !== null && total !== data.total)
        || data.items.length > PAGE_SIZE || products.length + data.items.length > data.total
        || (data.items.length === 0 && products.length < data.total)) {
      throw new Error('De classificatiegegevens zijn onvolledig of tijdens het laden veranderd.')
    }
    total = data.total
    for (const item of data.items) {
      if (!item.id || seenProductIds.has(item.id)) throw new Error('Dubbele Catalogusidentiteit.')
      seenProductIds.add(item.id)
      products.push(item)
    }
    for (const task of data.tasks) {
      if (!task.key || seenTaskKeys.has(task.key)) throw new Error('Dubbele classificatietaak.')
      seenTaskKeys.add(task.key)
      tasks.push(task)
    }
  } while (products.length < total)
  return { products, tasks }
}

export default function ArticleManagementWorkQueue({ isPlatformSuperuser = false, onOpenTask }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [activeType, setActiveType] = useState('')
  const [selectedKey, setSelectedKey] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setResult(null)
      setError('')
      setSelectedKey('')
      try {
        // Both existing GETs enforce canonical platform permissions server-side.
        // Opening this page never invokes the Superuser-only matching POST.
        const [sourceResponse, classification] = await Promise.all([
          fetchJsonWithAuth('/api/external-databases/articles-overview', {
            method: 'GET', signal: controller.signal,
          }),
          readFullClassificationWorkQueue(controller.signal),
        ])
        if (!sourceResponse.ok) throw new Error('De identificatietaken konden niet worden opgehaald.')
        const source = await sourceResponse.json().catch(() => ({}))
        if (!Array.isArray(source.items) || !Number.isSafeInteger(source.total)
            || source.total !== source.items.length) {
          throw new Error('Het bonartikeloverzicht is onvolledig.')
        }
        const queue = projectArticleWorkQueue(
          source.items, classification.products, classification.tasks,
          { isSuperuser: isPlatformSuperuser },
        )
        if (!controller.signal.aborted) setResult(queue)
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err.message || 'De werkvoorraad kon niet betrouwbaar worden gecontroleerd.')
          setResult(null)
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [revision, isPlatformSuperuser])

  const rows = useMemo(() => (result?.tasks || [])
    .filter((task) => !activeType || task.type === activeType)
    .map((task) => ({
      ...task, retailerLabel: RETAILERS[task.retailer] || task.retailer || '—',
      typeLabel: LABELS[task.type] || 'Onbekende taak',
    })), [result, activeType])
  const selected = rows.find((row) => row.key === selectedKey) || null

  function selectTask(row) {
    setSelectedKey((previous) => previous === row.key ? '' : row.key)
  }

  return <section aria-label="Artikelbeheer Werkvoorraad" data-testid="article-management-workqueue">
    <h3>Werkvoorraad</h3>
    <p>Inhuis toont alleen de resterende werkzaamheden op basis van bestaande bewezen artikelgegevens.
      Identificatie, echte synoniemen en classificatie zijn afzonderlijke onderdelen.
      Een artikel kan meer dan één classificatietaak hebben.</p>
    <div className="rz-external-ed2-counters" aria-label="Taaksoorten">
      <Button variant={activeType ? 'secondary' : 'primary'}
        aria-pressed={!activeType}
        onClick={() => { setActiveType(''); setSelectedKey('') }}>
        Alle taken{result ? ': ' + result.tasks.length : ''}
      </Button>
      {WORK_TYPES.filter((type) => type.key !== 'matching' || isPlatformSuperuser).map((type) =>
        <Button key={type.key} variant={activeType === type.key ? 'primary' : 'secondary'}
          aria-pressed={activeType === type.key}
          onClick={() => { setActiveType(type.key); setSelectedKey('') }}>
          {type.title}{result ? ': ' + result.counts[type.key] : ''}
        </Button>)}
    </div>
    {loading ? <p role="status">Werkvoorraad controleren...</p> : null}
    {error ? <p role="alert">Controle niet voltooid: {error} Er worden geen onbetrouwbare aantallen getoond.</p> : null}
    <div className="rz-mobile-table-bulk-actions">
      <Button variant="secondary" disabled={loading}
        onClick={() => setRevision((previous) => previous + 1)}>Opnieuw controleren</Button>
    </div>
    {result && !loading ? <>
      <p role="status" data-testid="article-workqueue-count-summary">
        {result.tasks.length} open taken in de getoonde taaksoorten.
        Dit is geen aantal unieke Catalogusartikelen; classificaties voor GS1 en CBS
        worden afzonderlijk geteld.
      </p>
      <DataTable columns={columns} data={rows} getRowKey={(item) => item.key}
        pageSize={10} dataTestId="article-workqueue-table"
        emptyMessage="Geen open taken voor dit type."
        renderRow={(item) => <tr key={item.key} tabIndex={0}
          aria-selected={selectedKey === item.key}
          className={selectedKey === item.key ? 'rz-row-selected' : ''}
          onClick={() => selectTask(item)}
          onDoubleClick={() => onOpenTask(item)}
          onKeyDown={(event) => {
            if (event.target !== event.currentTarget) return
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              selectTask(item)
            }
          }}>
          {columns.map((column) => <td key={column.key}>{item[column.key] || '—'}</td>)}
        </tr>} />
      <div className="rz-mobile-table-bulk-actions">
        <Button disabled={!selected}
          onClick={() => { if (selected) onOpenTask(selected) }}>
          {selected ? 'Naar ' + (selected.type === 'matching' ? 'Matchen'
            : selected.type === 'classify' ? 'Classificeren' : 'Identificeren')
            : 'Selecteer een taak'}
        </Button>
      </div>
      <p className="rz-external-databases-muted">
        Synoniemen: hiervoor is nog geen betrouwbare platformbrede telling van
        beoordeelbare voorstellen beschikbaar. Het bestaande werkgebied blijft
        beschikbaar; Inhuis toont geen fictieve nul.
      </p>
      <Button variant="secondary" onClick={() => onOpenTask({ area: 'synonyms' })}>
        Naar Synoniemen
      </Button>
    </> : null}
  </section>
}
