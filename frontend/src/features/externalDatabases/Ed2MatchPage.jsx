import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import Ed2CuratedMatchingBatch from './Ed2CuratedMatchingBatch'
import Ed2CourgetteFamilyPanel from './Ed2CourgetteFamilyPanel'
import { readMatchingOverview } from './ed2MatchingOverview.js'
import { matchingEntryAction } from './ed2MatchingProgressEntry.js'
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

export default function Ed2MatchPage({ initialReceiptItemId = '', forceNewCheckOnEntry = false }) {
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
  const [autoProgress, setAutoProgress] = useState({
    checked: 0, total: 0, check_number: 0, checks_completed: 0,
    estimated_checks: 5, overall_percent: 0, pass_number: 1,
    phase: 'voorbereiden', matched: 0,
  })

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

  const runAutomaticCheck = useCallback(async (forceNewCheck = false) => {
    if (!isSuperuser || !mountedRef.current || inFlightRef.current) return false
    inFlightRef.current = true
    setLoading(true)
    setAutoPhase('checking')
    setItems([])
    setLeftId('')
    setRightId('')
    setAutoProgress({
      checked: 0, total: 0, check_number: 0, checks_completed: 0,
      estimated_checks: 5, overall_percent: 0, pass_number: 1,
      phase: 'voorbereiden', matched: 0,
    })
    try {
      // A viewport breakpoint remounts this React page. Reattach to the
      // authorized server job instead of starting a fresh full-database scan.
      const statusResponse = await fetchJsonWithAuth('/api/catalog/ed2/bonnamen-matchen/progress')
      let job = await statusResponse.json().catch(() => ({}))
      if (!statusResponse.ok) {
        throw new Error('De voortgang van het matchen kon niet worden opgehaald.')
      }
      const action = matchingEntryAction(job, forceNewCheck)
      if (action === 'invalid') {
        throw new Error('Inhuis heeft een ongeldige matchingstatus teruggegeven.')
      }
      if (!mountedRef.current) return false
      if (action === 'start') {
        const started = await fetchJsonWithAuth('/api/catalog/ed2/bonnamen-matchen/progress/start', {
          method: 'POST',
        })
        job = await started.json().catch(() => ({}))
        if (!started.ok) {
          throw new Error('De achtergrondcontrole kon niet worden gestart (HTTP ' + started.status + ').')
        }
      }
      while (mountedRef.current) {
        if (job.ok !== true) {
          throw new Error('De voortgang van het matchen kon niet worden opgehaald.')
        }
        if (!mountedRef.current) return false
        if (!Number.isSafeInteger(job.checked) || !Number.isSafeInteger(job.total)
            || job.checked < 0 || job.total < 0 || job.checked > job.total
            || !Number.isSafeInteger(job.matched) || job.matched < 0
            || !Number.isSafeInteger(job.check_number) || job.check_number < 0
            || !Number.isSafeInteger(job.checks_completed) || job.checks_completed < 0
            || job.checks_completed > job.check_number
            || !Number.isSafeInteger(job.estimated_checks) || job.estimated_checks < 1
            || job.check_number > job.estimated_checks
            || !Number.isSafeInteger(job.overall_percent)
            || job.overall_percent < 0 || job.overall_percent > 100) {
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
        if (!mountedRef.current) return false
        const response = await fetchJsonWithAuth('/api/catalog/ed2/bonnamen-matchen/progress')
        job = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error('De voortgang van het matchen kon niet worden opgehaald.')
        }
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
    const task = window.setTimeout(() => { void runAutomaticCheck(forceNewCheckOnEntry) }, 0)
    return () => {
      mountedRef.current = false
      window.clearTimeout(task)
     }
  }, [isSuperuser, runAutomaticCheck, forceNewCheckOnEntry])

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
          const ready = await runAutomaticCheck(true)
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
    {autoPhase === 'checking' ? <div
      data-testid="ed2-auto-match-progress" role="group"
      aria-label="Voortgang automatisch matchen"
      className="rz-synonym-analysis-actions"
      style={{ display: 'grid', gap: '8px', width: 'min(100%, 520px)',
        marginInline: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <strong>Controle {autoProgress.check_number || 1}
          {autoProgress.total > 0
            ? ' · ' + autoProgress.checked.toLocaleString('nl-NL')
              + '/' + autoProgress.total.toLocaleString('nl-NL') : ''}
        </strong>
        <span data-testid="ed2-auto-match-overall-percent"
          title="Voorlopig totaal; extra matching kan aanvullende controles vereisen.">
          ca. {autoProgress.overall_percent}%
        </span>
      </div>
      <progress value={autoProgress.overall_percent} max={100}
        aria-label="Voorlopige totale voortgang van het matchen"
        style={{ width: '100%', accentColor: 'var(--color-ui-primary)' }} />
    </div> : null}
    {autoPhase === 'error' ? <Button onClick={() => { void runAutomaticCheck(true) }}>
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
        ? <Ed2CourgetteFamilyPanel item={left} onConfirmed={() => { void runAutomaticCheck(true) }} /> : null}
      <details className="rz-match-tools">
        <summary>Bonnaamregels en familie-uitzonderingen</summary>
        <Ed2CuratedMatchingBatch autoOnEntryMode onConfirmed={() => { void runAutomaticCheck(true) }} />
      </details>
    </> : null}
  </section>
}
