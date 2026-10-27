import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
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
  const location = useLocation()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedItem, setSelectedItem] = useState(null)
  const [offLinkOutcome, setOffLinkOutcome] = useState(() => location.state?.offLinkOutcome || null)
  const isMobile = useMobileAppViewport()

  useEffect(() => {
    const result = location.state?.offLinkOutcome
    if (!result) return undefined
    setOffLinkOutcome(result)
    if (result.status !== 'success') return undefined
    const timeout = window.setTimeout(() => setOffLinkOutcome(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [location.key, location.state?.offLinkOutcome])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetchJsonWithAuth('/api/external-databases/unlinked-articles', { method: 'GET' })
        const payload = await response.json()
        if (!response.ok) throw new Error('De artikelen konden niet worden geladen.')
        if (!cancelled) {
          const loadedItems = (payload.items || []).map((item) => ({
            ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
          }))
          setItems(loadedItems)
          if (location.state?.selectedItemId) {
            setSelectedItem(loadedItems.find((item) => item.id === location.state.selectedItemId) || null)
          }
        }
      } catch {
        if (!cancelled) setError('De artikelen konden niet worden geladen.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [location.state?.selectedItemId])

  return (
    <AppShell title="Externe databases 2" showExit={false}>
      <ScreenCard fullWidth>
        <h2>Externe databases 2</h2>
        <p>{isMobile ? 'Tik' : 'Dubbelklik'} op een artikel om passende productkandidaten te zoeken.</p>
        {offLinkOutcome ? <p data-testid="external-off-link-outcome"
          role={offLinkOutcome.status === 'success' ? 'status' : 'alert'}
          onClick={() => setOffLinkOutcome(null)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') setOffLinkOutcome(null)
          }}
          tabIndex={0}
          title={offLinkOutcome.status === 'success' ? '' : 'Klik om deze melding te sluiten'}>
          {offLinkOutcome.message}
        </p> : null}
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
