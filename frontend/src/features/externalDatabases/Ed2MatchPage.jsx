import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import Ed2CuratedMatchingBatch from './Ed2CuratedMatchingBatch'
import Ed2CourgetteFamilyPanel from './Ed2CourgetteFamilyPanel'
import { readMatchingOverview } from './ed2MatchingOverview.js'
import '../articleSynonyms/synonymAnalysis.css'

const RETAILERS = {
  ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', jumbo: 'Jumbo',
  lidl: 'Lidl', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic',
}
const columns = [
  { key: 'selected', label: '', width: 44 },
  { key: 'receipt_line_text', label: 'Artikel', width: 210, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 108, sortable: true, filterable: true },
  { key: 'receipt_article_number', label: 'Bonartikelnummer', width: 126, sortable: true, filterable: true },
  { key: 'barcode', label: 'Art./Barcode', width: 145, sortable: true, filterable: true },
]

function curatedCourgette(value) {
  const words = String(value || '').toLocaleLowerCase('nl')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .match(/[a-z0-9]+/g) || []
  const base = new Set(['courgette', 'courgettes'])
  const allowed = new Set([...base, 'bio', 'biologisch', 'biologische',
    'groen', 'groene', 'geel', 'gele', 'ah', 'jumbo', 'lidl', 'albert', 'heijn'])
  const colors = [words.some((w) => w === 'groen' || w === 'groene'),
    words.some((w) => w === 'geel' || w === 'gele')]
  return words.filter((w) => base.has(w)).length === 1
    && words.every((w) => allowed.has(w)) && !colors.every(Boolean)
}

function displayRow(item) {
  return { ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
    barcode: item.article_code || item.manual_barcode || '' }
}

function confirmedTarget(item) {
  if (item.identity_status !== 'catalog_linked') return false
  const explicit = String(item.identity_catalog_product_id || '')
  const central = String(item.catalog_product_id || '')
  return Boolean(explicit || central) && !(explicit && central && explicit !== central)
    && Boolean(String(item.receipt_article_number || '') || item.article_code)
    && !(item.article_code && item.manual_barcode && item.article_code !== item.manual_barcode)
}

function needsManualMatching(item) {
  // The backend assigns a review reason only if multiple distinct confirmed
  // Catalogus identities exist for this retailer-neutral receipt name.
  // A generic unrecognized article is not a manual matching proposal.
  return item.identity_status === 'not_identified'
    && !item.article_code && !item.manual_barcode
    && !item.identity_catalog_product_id && !item.catalog_product_id
    && Boolean(String(item.automatic_match_review_reason || '').trim())
}

export default function Ed2MatchPage({ initialReceiptItemId = '' }) {
  const { showFeedback } = useAppFeedback()
  const isSuperuser = Boolean(readStoredAuthContext()?.is_platform_superuser)
  const mountedRef = useRef(false)
  const inFlightRef = useRef(false)
  const [items, setItems] = useState([])
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [autoPhase, setAutoPhase] = useState('checking')
  const [autoResult, setAutoResult] = useState({ linked: 0, passes: 0 })
  const [autoProgress, setAutoProgress] = useState({ checked: 0, total: 0, pass_number: 1, phase: 'voorbereiden', matched: 0 })

  const reload = useCallback(async () => {
    const response = await fetchJsonWithAuth('/api/external-databases/articles-overview')
    if (!response.ok) throw new Error('Het actuele bonartikeloverzicht kon niet worden opgehaald.')
    const payload = await response.json()
    if (!Array.isArray(payload.items)) {
      throw new Error('Inhuis heeft geen geldig bonartikeloverzicht teruggegeven.')
    }
    if (mountedRef.current) {
      const loaded = payload.items.map(displayRow)
      setItems(loaded)
      if (initialReceiptItemId && loaded.some((item) => item.id === initialReceiptItemId && needsManualMatching(item))) {
        setLeftId(initialReceiptItemId)
      }
    }
  }, [initialReceiptItemId])

  const runAutomaticCheck = useCallback(async () => {
    if (!isSuperuser || !mountedRef.current || inFlightRef.current) return false
    inFlightRef.current = true
    setLoading(true)
    setAutoPhase('checking')
    setItems([])
    setLeftId('')
    setRightId('')
    setAutoProgress({ checked: 0, total: 0, pass_number: 1, phase: 'voorbereiden', matched: 0 })
    try {
      const started = await fetchJsonWithAuth('/api/catalog/ed2/bonnamen-matchen/progress/start', {
        method: 'POST',
      })
      if (!started.ok) {
        throw new Error('De achtergrondcontrole kon niet worden gestart (HTTP ' + started.status + ').')
      }
      while (mountedRef.current) {
        const response = await fetchJsonWithAuth('/api/catalog/ed2/bonnamen-matchen/progress')
        const job = await response.json().catch(() => ({}))
        if (!response.ok || job.ok !== true) {
          throw new Error('De voortgang van het matchen kon niet worden opgehaald.')
        }
        if (!mountedRef.current) return false
        if (!Number.isSafeInteger(job.checked) || !Number.isSafeInteger(job.total)
            || job.checked < 0 || job.total < 0 || job.checked > job.total
            || !Number.isSafeInteger(job.matched) || job.matched < 0) {
          throw new Error('Inhuis heeft een ongeldige voortgang teruggegeven.')
        }
        setAutoProgress(job)
        if (job.state === 'error') {
          throw new Error(job.error || 'De automatische matching is niet afgerond.')
        }
        if (job.state === 'completed') {
          const stableOverview = readMatchingOverview({
            ok: true, barcode_written: false, linked: 0, limit_reached: false,
            matching_overview: job.matching_overview,
          })
          if (stableOverview) {
            const loaded = stableOverview.map(displayRow)
            setItems(loaded)
            if (initialReceiptItemId && loaded.some((item) =>
              item.id === initialReceiptItemId && needsManualMatching(item))) {
              setLeftId(initialReceiptItemId)
            }
          } else {
            // An incomplete final proof still falls back to the canonical GET.
            await reload()
          }
          if (!mountedRef.current) return false
          setAutoResult({ linked: job.matched, passes: job.pass_number })
          setAutoPhase('ready')
          return true
        }
        if (job.state !== 'running') throw new Error('Onbekende matchingstatus.')
        await new Promise((resolve) => window.setTimeout(resolve, 750))
      }
      return false
    } catch (error) {
      if (mountedRef.current) {
        setAutoPhase('error')
        setItems([])
        showFeedback({
          key: 'ed2-match-entry-error', variant: 'error',
          title: 'Automatische matching niet afgerond',
          message: (error.message || 'De controle is mislukt.')
            + ' De handmatige matchinglijst blijft gesloten. '
            + 'Eerdere voltooide batches kunnen al zijn opgeslagen; opnieuw controleren is veilig.',
        })
      }
      return false
    } finally {
      inFlightRef.current = false
      if (mountedRef.current) setLoading(false)
    }
  }, [isSuperuser, showFeedback, reload, initialReceiptItemId])

  useEffect(() => {
    if (!isSuperuser) return undefined
    mountedRef.current = true
    // Delay one task to avoid duplicate POSTs in React StrictMode effect replay.
    const task = window.setTimeout(() => { void runAutomaticCheck() }, 0)
    return () => {
      mountedRef.current = false
      window.clearTimeout(task)
     }
  }, [isSuperuser, runAutomaticCheck])

  const leftRows = useMemo(() => items.filter(needsManualMatching), [items])
  const rightRows = useMemo(() => items.filter(confirmedTarget), [items])
  const left = leftRows.find((item) => item.id === leftId)
  const right = rightRows.find((item) => item.id === rightId)

  function matchSelected() {
    if (!left || !right || saving || loading || autoPhase !== 'ready') return
    showFeedback({
      variant: 'warning', title: 'Bonartikelen matchen?',
      message: left.receipt_line_text + ' (' + left.retailer + ') koppelen aan hetzelfde Catalogusproduct als '
        + right.receipt_line_text + ' (' + right.retailer + ')?',
      detail: 'Inhuis controleert beide bonartikelidentiteiten opnieuw. Er wordt geen barcode overgenomen, geen Catalogusproduct aangemaakt en geen voorraad gewijzigd. Alleen deze specifieke bonartikelcombinatie wordt gekoppeld.',
      primaryActionLabel: 'Match bevestigen', secondaryActionLabel: 'Annuleren',
      testId: 'ed2-manual-match-confirm',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-receipt-match/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              source_receipt_item_id: left.id, target_receipt_item_id: right.id,
            }),
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || payload.ok !== true) {
            throw new Error(typeof payload.detail === 'string' ? payload.detail
              : 'De match is niet bevestigd.')
          }
          // A new human-confirmed product can unlock further automatic proofs.
          const ready = await runAutomaticCheck()
          if (ready && mountedRef.current) {
            showFeedback({ variant: 'success', title: 'Bonartikel gematcht',
              message: 'De Catalogusidentiteit is gekoppeld en de automatische controle is bijgewerkt. Er is geen barcode overgenomen.' })
          }
        } catch (error) {
          showFeedback({ variant: 'error', title: 'Matching niet verwerkt',
            message: error.message || 'Controleer de actuele gegevens.' })
        } finally { setSaving(false) }
        return false
      },
    })
  }

  function selectCell(item, selectedId, setSelectedId) {
    if (saving || loading || autoPhase !== 'ready') return
    setSelectedId(item.id === selectedId ? '' : item.id)
  }

  function articleTable(rows, chosen, setChosen, side) {
    return <DataTable columns={columns} data={rows} getRowKey={(item) => item.id}
      pageSize={10} wrapperClassName="rz-synonym-analysis-table-wrapper"
      dataTestId={'ed2-match-' + side + '-table'}
      paginationActions={<span className="rz-synonym-pagination-spacer" aria-hidden="true" />}
      emptyMessage={side === 'left' ? 'Geen handmatig te matchen artikelen.'
        : 'Geen bewezen Catalogusartikelen beschikbaar.'}
      renderRow={(item) => <tr key={item.id} tabIndex={0}
        className="rz-synonym-analysis-main-row" aria-selected={chosen === item.id}
        onClick={() => selectCell(item, chosen, setChosen)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            selectCell(item, chosen, setChosen)
          }
        }}>
        <td><input type="checkbox" checked={chosen === item.id}
          disabled={saving || loading}
          aria-label={(side === 'left' ? 'Selecteer links ' : 'Selecteer rechts ')
            + item.receipt_line_text + ', ' + item.retailer
            + ', bonartikelnummer ' + (item.receipt_article_number || 'ontbreekt')}
          onClick={(event) => event.stopPropagation()}
          onChange={() => selectCell(item, chosen, setChosen)} /></td>
        <td>{item.receipt_line_text}
          {item.automatic_match_review_reason ? <span className="rz-synonym-review-hint"
            title={item.automatic_match_review_reason}>{item.automatic_match_review_reason}</span> : null}</td>
        <td>{item.retailer}</td>
        <td>{item.receipt_article_number || '—'}</td>
        <td>{item.barcode || '—'}</td>
      </tr>} />
  }

  if (!isSuperuser) return <p>Matchen is uitsluitend beschikbaar voor de Superuser.</p>

  return <section aria-label="Bonartikelen matchen" data-testid="ed2-match-workspace">
    <h2>Matchen</h2>
    <p>Inhuis matcht bij het openen eerst alle veilig automatisch herkenbare bonartikelen.
      Daarna staan links alleen artikelen met verschillende bevestigde Catalogusuitvoeringen,
      waarvoor je handmatig het juiste artikel rechts kunt kiezen.</p>
    {autoPhase === 'checking' ? <div role="status" aria-live="polite"
      data-testid="ed2-auto-match-progress"
      className="rz-synonym-analysis-actions">
      <strong>Automatische artikelmatching controleren</strong>
      <p>Fase: {autoProgress.phase === 'voorbereiden'
        ? 'Voorbereiden' : autoProgress.phase}.</p>
      <p>Controle {autoProgress.pass_number}: {autoProgress.total > 0
        ? autoProgress.checked + ' van ' + autoProgress.total
          + ' bonartikelen gecontroleerd ('
          + Math.floor((autoProgress.checked / autoProgress.total) * 100)
          + '% van deze controleronde)'
        : '0 bonartikelen gecontroleerd; de volledige lijst wordt voorbereid.'}</p>
      {autoProgress.total > 0 ? <progress value={autoProgress.checked}
        max={autoProgress.total} aria-label="Gecontroleerde bonartikelen"
        style={{ width: '100%', accentColor: 'var(--color-ui-primary)' }} /> : null}
      <p>{autoProgress.matched} bonartikel(en) automatisch gekoppeld.
        De controle loopt door als je naar een ander scherm gaat.</p>
    </div> : null}
    {autoPhase === 'error' ? <Button onClick={() => { void runAutomaticCheck() }}>
      Automatische controle opnieuw uitvoeren
    </Button> : null}
    {autoPhase === 'ready' ? <>
      <div className="rz-synonym-side-by-side">
        <section className="rz-synonym-side" aria-label="Bonartikelen links">
          <div className="rz-synonym-side-heading"><h3>Handmatig matchen</h3>
            <span>{leftRows.length} handmatig te matchen</span></div>
          {articleTable(leftRows, leftId, setLeftId, 'left')}
          <div className="rz-synonym-actions-placeholder" aria-hidden="true" />
        </section>
        <section className="rz-synonym-side" aria-label="Bonartikelen rechts">
          <div className="rz-synonym-side-heading"><h3>Te koppelen artikelen</h3>
            <span>{rightRows.length} bewezen</span></div>
          {articleTable(rightRows, rightId, setRightId, 'right')}
          <div className="rz-synonym-analysis-actions">
            <Button disabled={!left || !right || saving || loading} onClick={matchSelected}>
              {saving ? 'Matchen...' : 'Bonartikel matchen'}
            </Button>
          </div>
        </section>
      </div>
      <p data-testid="ed2-auto-match-summary">
        Bij het openen automatisch gematcht: {autoResult.linked}.
        Artikelen zonder geschikte bewezen match blijven onder Identificeren beschikbaar.
      </p>
      {left && !left.article_code && !left.manual_barcode && curatedCourgette(left.receipt_line_text)
        ? <Ed2CourgetteFamilyPanel item={left} onConfirmed={() => { void runAutomaticCheck() }} /> : null}
      <details className="rz-match-tools">
        <summary>Bonnaamregels en familie-uitzonderingen</summary>
        <Ed2CuratedMatchingBatch autoOnEntryMode onConfirmed={() => { void runAutomaticCheck() }} />
      </details>
    </> : null}
  </section>
}
