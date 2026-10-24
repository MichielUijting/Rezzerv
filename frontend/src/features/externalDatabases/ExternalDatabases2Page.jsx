import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useMobileAppViewport } from '../../app/mobileViewport'
import OffCandidatePanel from './OffCandidatePanel'
import './externalDatabases.css'

const RETAILERS = { ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', lidl: 'Lidl', jumbo: 'Jumbo', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic' }
const columns = [
  { key: 'receipt_line_text', label: 'Artikel', width: 320, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 170, sortable: true, filterable: true },
  { key: 'receipt_article_number', label: 'Bonartikelnummer', width: 190, sortable: true, filterable: true },
  { key: 'quantity_label', label: 'Omvang / gewicht', width: 170, sortable: true, filterable: true },
]

export default function ExternalDatabases2Page() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedItem, setSelectedItem] = useState(null)
  const isMobile = useMobileAppViewport()

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetchJsonWithAuth('/api/external-databases/unlinked-articles', { method: 'GET' })
        const payload = await response.json()
        if (!response.ok) throw new Error('De artikelen konden niet worden geladen.')
        if (!cancelled) setItems((payload.items || []).map((item) => ({
          ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
        })))
      } catch {
        if (!cancelled) setError('De artikelen konden niet worden geladen.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  return (
    <AppShell title="Externe databases 2" showExit={false}>
      <ScreenCard fullWidth>
        <h2>Externe databases 2</h2>
        <p>{isMobile ? 'Tik' : 'Dubbelklik'} op een artikel om passende OFF-kandidaten te zoeken.</p>
        {error ? <p role="alert">{error}</p> : null}
        <div className="rz-external-receipt-overview">
        <DataTable
          columns={columns}
          data={items}
          getRowKey={(item) => item.id}
          defaultSort={{ key: 'receipt_line_text', direction: 'asc' }}
          emptyMessage={loading ? 'Artikelen laden...' : error ? 'Artikelen niet beschikbaar.' : 'Geen artikelen zonder barcodekoppeling in de Catalogus.'}
          dataTestId="external-databases-2-table"
          renderRow={(item) => <tr key={item.id}
            tabIndex={0}
            aria-selected={selectedItem?.id === item.id}
            className={selectedItem?.id === item.id ? 'rz-row-selected' : ''}
            onClick={() => { if (isMobile) setSelectedItem(item) }}
            onDoubleClick={() => { if (!isMobile) setSelectedItem(item) }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedItem(item) }
            }}
          >{columns.map((column) => <td key={column.key}>{item[column.key]}</td>)}</tr>}
        />
        {selectedItem ? <OffCandidatePanel key={selectedItem.id} item={selectedItem} /> : null}
        </div>
      </ScreenCard>
    </AppShell>
  )
}
