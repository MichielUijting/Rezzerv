import { useEffect, useRef, useState } from 'react'
import Button from '../../ui/Button'
import ClassificationSearchOverlay from './ClassificationSearchOverlay.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

const API = '/api/cbs-classifications'

async function readCbs(path, options = {}) {
  const response = await fetchJsonWithAuth(API + path, options)
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(
    typeof result.detail === 'string' ? result.detail : 'CBS-gegevens konden niet worden geladen.'
  )
  return result
}

function checkSnapshots(response, ids) {
  if (response.total !== ids.length || !Array.isArray(response.items)
      || response.items.length !== ids.length) {
    throw new Error('De Catalogusselectie is veranderd. Ververs de selectie.')
  }
  const byId = new Map(response.items.map((item) => [item.id, item]))
  if (byId.size !== ids.length || ids.some((id) => {
    const item = byId.get(id)
    return !item || !String(item.name || '').trim()
      || !Number.isSafeInteger(item.version) || item.version < 0
      || typeof item.classified !== 'boolean'
  })) throw new Error('Ongeldige actuele CBS-gegevens. Ververs de selectie.')
  return ids.map((id) => byId.get(id))
}

export default function CbsBulkClassificationActions({ selectedIds, disabled = false, onSaved }) {
  const { showFeedback } = useAppFeedback()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState([])
  const [trail, setTrail] = useState([])
  const [chosen, setChosen] = useState(null)
  const [looking, setLooking] = useState(false)
  const [busy, setBusy] = useState(false)
  const ticketRef = useRef(0)
  const abortRef = useRef(null)
  const frozenIds = useRef([])

  useEffect(() => () => { abortRef.current?.abort(); ticketRef.current += 1 }, [])

  function selection() {
    if (disabled || busy || !selectedIds.length) return null
    if (selectedIds.length > 100 || new Set(selectedIds).size !== selectedIds.length) {
      showFeedback({ variant: 'warning',
        message: 'Selecteer maximaal 100 verschillende Catalogusartikelen voor een CBS-bulkactie.' })
      return null
    }
    return [...selectedIds]
  }

  function close() {
    abortRef.current?.abort()
    ticketRef.current += 1
    setOpen(false)
    setLooking(false)
    setChosen(null)
  }

  async function browse(parent = null, path = []) {
    const ticket = ++ticketRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setQuery('')
    setRows([])
    setChosen(null)
    setTrail(path)
    setLooking(true)
    try {
      const url = '/categories/browse' + (parent ? '?parent_code=' + encodeURIComponent(parent) : '')
      const result = await readCbs(url, { signal: controller.signal })
      if (!controller.signal.aborted && ticket === ticketRef.current) {
        setRows(Array.isArray(result.items) ? result.items : [])
      }
    } catch (err) {
      if (!controller.signal.aborted && ticket === ticketRef.current) {
        showFeedback({ variant: 'error', message: err.message })
      }
    } finally {
      if (ticket === ticketRef.current) setLooking(false)
    }
  }

  useEffect(() => {
    if (!open || query.trim().length < 2) return undefined
    const needle = query.trim()
    const ticket = ++ticketRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLooking(true)
    const timer = window.setTimeout(async () => {
      try {
        let result = await readCbs('/categories?query=' + encodeURIComponent(needle) + '&limit=50',
          { signal: controller.signal })
        if (!result.items?.length) {
          result = await readCbs('/categories/suggest?query=' + encodeURIComponent(needle) + '&limit=50',
            { signal: controller.signal })
        }
        if (!controller.signal.aborted && ticket === ticketRef.current) {
          setRows(Array.isArray(result.items) ? result.items : [])
        }
      } catch (err) {
        if (!controller.signal.aborted && ticket === ticketRef.current) {
          showFeedback({ variant: 'error', message: err.message })
        }
      } finally {
        if (ticket === ticketRef.current) setLooking(false)
      }
    }, 250)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, open, showFeedback])

  function openChooser() {
    const ids = selection()
    if (!ids) return
    frozenIds.current = ids
    setOpen(true)
    void browse()
  }

  async function prepare(mode, ids, category = null) {
    if (busy) return
    if (mode === 'confirm' && (!category?.lowest || !category.cbs_code || !category.reference_version)) {
      showFeedback({ variant: 'warning', message: 'Kies een officiële CBS-eindcategorie.' })
      return
    }
    setBusy(true)
    try {
      const result = await readCbs('/workqueue-selected-cbs-snapshots', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_ids: ids }),
      })
      const snapshot = checkSnapshots(result, ids)
      if (mode === 'remove' && snapshot.some((item) => !item.classified || item.version < 1)) {
        throw new Error('Selecteer voor verwijderen uitsluitend artikelen met een actieve CBS-classificatie.')
      }
      const selections = snapshot.map((item) => ({
        global_product_id: item.id,
        expected_product_name: item.name,
        expected_version: item.version,
        ...(mode === 'confirm'
          ? { cbs_code: category.cbs_code, reference_version: category.reference_version }
          : {}),
      }))
      if (mode === 'confirm') close()
      showFeedback({
        variant: 'warning',
        title: mode === 'confirm' ? 'CBS-classificaties toekennen' : 'CBS-classificaties verwijderen',
        message: mode === 'confirm'
          ? category.cbs_code + ' — ' + category.name_nl + ' toekennen aan '
            + ids.length + ' artikelen?'
          : 'De CBS-classificatie van ' + ids.length + ' artikelen verwijderen?',
        detail: mode === 'confirm'
          ? 'Bestaande CBS-classificaties kunnen worden vervangen. GS1, productidentiteiten en voorraad blijven behouden.'
          : 'Alleen de actieve CBS-classificaties worden verwijderd. Producten, barcodes en geschiedenis blijven behouden.',
        primaryActionLabel: 'Bevestigen',
        secondaryActionLabel: 'Annuleren',
        onPrimaryAction: async () => {
          setBusy(true)
          try {
            const updated = await readCbs(mode === 'confirm' ? '/bulk-confirm' : '/bulk-remove', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ selections }),
            })
            onSaved()
            showFeedback({ variant: 'success', message: mode === 'confirm'
              ? updated.confirmed + ' CBS-classificaties vastgelegd; '
                + updated.unchanged + ' ongewijzigd.'
              : updated.removed + ' CBS-classificaties verwijderd.' })
          } finally {
            setBusy(false)
          }
        },
      })
    } catch (err) {
      showFeedback({ variant: 'error',
        message: err.message || 'De CBS-bulkactie kon niet worden voorbereid.' })
    } finally {
      setBusy(false)
    }
  }

  return <div className="rz-mobile-table-bulk-actions" aria-label="CBS-bulkacties"
    data-testid="classification-cbs-bulk-actions">
    <Button type="button" variant="secondary" disabled={disabled || busy || !selectedIds.length}
      onClick={openChooser} data-testid="classification-cbs-bulk-assign">
      CBS-classificatie toekennen
    </Button>
    <Button type="button" variant="secondary" disabled={disabled || busy || !selectedIds.length}
      onClick={() => { const ids = selection(); if (ids) void prepare('remove', ids) }}
      data-testid="classification-cbs-bulk-remove">
      CBS-classificatie verwijderen
    </Button>
    {selectedIds.length > 100 ? <span role="status">
      Maximaal 100 artikelen per CBS-bulkactie; exportselecties blijven behouden.
    </span> : null}
    {open ? <ClassificationSearchOverlay
      title="CBS-categorie voor geselecteerde artikelen"
      query={query} rows={rows} busy={looking || busy}
      onQueryChange={(value) => {
        ticketRef.current += 1
        abortRef.current?.abort()
        setQuery(value)
        setTrail([])
        setChosen(null)
        setRows([])
      }}
      onClose={close}
      onChoose={(item) => {
        if (item.lowest) setChosen(item)
        else void browse(item.cbs_code, [...trail, { code: item.cbs_code, name: item.name_nl }])
      }}
      getKey={(item) => item.cbs_code}
      getTitle={(item) => item.cbs_code + ' — ' + item.name_nl}
      getDetail={(item) => item.path || (item.lowest ? 'Definitieve categorie' : 'Open subcategorieën')}
      emptyMessage="Zoek of blader door de officiële CBS-classificaties."
    >
      <div className="rz-classification-overlay-controls">
        <Button type="button" variant="secondary" disabled={looking || busy}
          onClick={() => { void browse() }}>CBS-hoofdcategorieën</Button>
        {trail.length ? <Button type="button" variant="secondary" disabled={looking || busy}
          onClick={() => {
            const parent = trail.length > 1 ? trail[trail.length - 2].code : null
            void browse(parent, trail.slice(0, -1))
          }}>Een niveau terug</Button> : null}
        {chosen ? <p role="status" data-testid="classification-cbs-bulk-chosen">
          Gekozen: {chosen.cbs_code} — {chosen.name_nl}
        </p> : null}
        <Button type="button" disabled={!chosen || looking || busy}
          data-testid="classification-cbs-bulk-confirm-choice"
          onClick={() => { void prepare('confirm', frozenIds.current, chosen) }}>
          Toekennen aan {frozenIds.current.length} geselecteerde artikelen
        </Button>
      </div>
    </ClassificationSearchOverlay> : null}
  </div>
}
