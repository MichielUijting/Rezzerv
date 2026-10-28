import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'

const API = '/api/catalog/shopify'
const BATCH_SIZE = 100
const OFF_INTERVAL_MS = 6200

async function call(url, options) {
  const response = await fetchJsonWithAuth(url, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : 'Verzoek mislukt.')
    error.status = response.status
    throw error
  }
  return body
}

const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))

export default function ShopifyReviewPage() {
  const { showFeedback } = useAppFeedback()
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [proposals, setProposals] = useState({})
  const [loading, setLoading] = useState(true)
  const [fetching, setFetching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [reload, setReload] = useState(0)
  const busyRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setItems([])
    setSelected(new Set())
    setProposals({})
    setError('')
    async function load() {
      try {
        const all = []
        let total = null
        do {
          const data = await call(API + '?limit=' + BATCH_SIZE + '&offset=' + all.length,
            { signal: controller.signal })
          if (controller.signal.aborted) return
          const batch = Array.isArray(data.items) ? data.items : []
          if (!batch.length && Number(data.total || 0) > all.length) {
            throw new Error('Cataloguslijst is onvolledig geladen.')
          }
          all.push(...batch)
          total = Number(data.total || 0)
        } while (all.length < total)
        if (!controller.signal.aborted) setItems(all)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [reload])

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectedItems = useMemo(() => items.filter((item) => selected.has(item.id)), [items, selected])
  const allHaveProposals = selectedItems.length > 0 && selectedItems.every(
    (item) => proposals[item.id]?.shopify_id && proposals[item.id]?.gtin === item.gtin
  )

  async function fetchProposals() {
    if (busyRef.current || !selectedItems.length) return
    const pending = selectedItems.filter((item) => (
      !proposals[item.id]?.shopify_id || proposals[item.id]?.gtin !== item.gtin
    ))
    if (!pending.length) {
      setNote('Voor alle geselecteerde artikelen is al een voorstel opgehaald.')
      return
    }
    busyRef.current = true
    setFetching(true)
    setError('')
    let found = 0
    try {
      for (let index = 0; index < pending.length; index += 1) {
        if (index > 0) await sleep(OFF_INTERVAL_MS)
        const item = pending[index]
        setNote('OFF-voorstellen ophalen: ' + (index + 1) + ' van ' + pending.length)
        try {
          let result
          try {
            result = await call(API + '/' + encodeURIComponent(item.id) + '/proposal')
          } catch (err) {
            if (err.status !== 429) throw err
            await sleep(OFF_INTERVAL_MS)
            result = await call(API + '/' + encodeURIComponent(item.id) + '/proposal')
          }
          if (result.gtin !== item.gtin) {
            throw new Error('De barcode is gewijzigd. Ververs de pagina.')
          }
          if (result.shopify_id) found += 1
          setProposals((current) => ({ ...current, [item.id]: result }))
        } catch (err) {
          setProposals((current) => ({
            ...current,
            [item.id]: { gtin: item.gtin, shopify_id: '', status: 'Geen voorstel',
              message: err.message },
          }))
        }
      }
      setNote(found + ' van ' + pending.length + ' artikelen hebben een onbevestigd voorstel. Controleer de tabel voordat je bevestigt.')
    } finally {
      busyRef.current = false
      setFetching(false)
    }
  }

  async function confirmProposals() {
    if (busyRef.current || !allHaveProposals || selectedItems.length > 100) return
    const selections = selectedItems.map((item) => ({
      global_product_id: item.id,
      expected_gtin: item.gtin,
      expected_version: item.version,
      shopify_id: proposals[item.id].shopify_id,
      // De afzonderlijke bevestigingsactie is de menselijke controle.
      barcode_confirmed: true,
    }))
    busyRef.current = true
    setSaving(true)
    setError('')
    try {
      const data = await call(API + '/bulk-confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections }),
      })
      showFeedback({ variant: 'success', message: data.confirmed + ' artikelclassificaties bevestigd.' })
      setNote(data.confirmed + ' classificaties definitief in de Catalogus vastgelegd.')
      setReload((value) => value + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      busyRef.current = false
      setSaving(false)
    }
  }

  const busy = loading || fetching || saving
  const columns = [
    {
      key: 'select', label: '', width: 48, className: 'rz-check', cellClassName: 'rz-check',
      renderCell: (item) => <input type="checkbox"
        aria-label={'Selecteer ' + item.name + ' (' + item.gtin + ')'}
        checked={selected.has(item.id)}
        disabled={busy || (!selected.has(item.id) && selected.size >= 100)}
        onChange={() => toggle(item.id)} />,
    },
    {
      key: 'name', label: 'Artikel', width: 235, sortable: true, filterable: true,
      getFilterValue: (item) => [item.name, item.brand].join(' '),
      renderCell: (item) => <div>{item.name}{item.brand ? <div className="rz-external-databases-muted">{item.brand}</div> : null}</div>,
    },
    { key: 'gtin', label: 'Barcode', width: 125, sortable: true, filterable: true },
    {
      key: 'shopify_path', label: 'Huidige artikelclassificatie', width: 250, sortable: true, filterable: true,
      renderCell: (item) => <span title={item.shopify_path || ''}>{item.shopify_path || 'Niet geclassificeerd'}</span>,
    },
    {
      key: 'proposal', label: 'Voorgestelde artikelclassificatie', width: 300,
      filterable: true, sortable: true,
      getValue: (item) => proposals[item.id]?.shopify_path || proposals[item.id]?.status || '',
      renderCell: (item) => {
        const proposal = proposals[item.id]
        if (!proposal) return 'Nog geen voorstel opgehaald'
        if (!proposal.shopify_id) {
          return <span title={proposal.message || ''}>{proposal.message || 'Geen voorstel beschikbaar'}</span>
        }
        return <div>
          <span title={proposal.shopify_path}>{proposal.shopify_path}</span>
          {proposal.warning ? <div className="rz-external-databases-muted">{proposal.warning}</div> : null}
          <div className="rz-external-databases-muted">Nog niet bevestigd</div>
        </div>
      },
    },
  ]

  return <AppShell title="Artikelclassificaties toekennen" showExit={false}>
    <ScreenCard fullWidth>
      <h2>Artikelclassificaties toekennen</h2>
      <p>Via OFF kun je suggesties opvragen voor de artikelclassificatie.</p>
      {error ? <p role="alert">{error}</p> : null}
      {note ? <p role="status">{note}</p> : null}
      <DataTable dataTestId="shopify-review-table" columns={columns} data={items}
        getRowKey={(item) => item.id} pageSize={8}
        emptyMessage={loading ? 'Artikelen laden...' : 'Geen Catalogusartikelen met geldige barcode gevonden.'}
        paginationActions={<>
          <span aria-live="polite">{selected.size} geselecteerd</span>
          <Button type="button" disabled={busy || !selected.size} onClick={fetchProposals}>
            {fetching ? 'Voorstellen ophalen...' : 'Voorstel ophalen'}
          </Button>
          <Button type="button" disabled={busy || !allHaveProposals} onClick={confirmProposals}>
            {saving ? 'Bevestigen...' : 'Voorstel bevestigen'}
          </Button>
        </>} />
    </ScreenCard>
  </AppShell>
}
