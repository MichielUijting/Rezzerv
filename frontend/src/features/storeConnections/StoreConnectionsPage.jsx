import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import DataTable from '../../ui/DataTable.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared.jsx'
import {
  LIDL_BOOKMARKLET_VERSION,
  LIDL_HISTORY_URL,
  LIDL_WEB_ORIGIN,
  buildLidlWebBookmarklet,
  buildLidlWebPageScript,
} from './lidlWebReceiptBridge.js'
import {
  JUMBO_BOOKMARKLET_VERSION,
  JUMBO_ORDERS_URL,
  JUMBO_POC_FRAGMENT_PREFIX,
  buildJumboPocBookmarklet,
} from './jumboReceiptPocBridge.js'
import { buildJumboImportEnvelope } from './jumboReceiptImport.js'
import { jumboDateWindow, importJumboBatch } from './jumboReceiptBatch.js'
import { deriveStoreConnectionRows, formatLastSync } from './storeConnectionsModel.js'
import PicnicAccountResearchPanel from './PicnicAccountResearchPanel.jsx'

export default function StoreConnectionsPage() {
  const { showFeedback, dismissFeedbackIfKey } = useAppFeedback()
  const ahSyncPageMountedRef = useRef(false)
  const lidlImportPageMountedRef = useRef(false)
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [editingCode, setEditingCode] = useState('')
  const [cardNumber, setCardNumber] = useState('')
  const [ahConnection, setAhConnection] = useState({ connected: false, persistence: 'encrypted_database' })
  const [ahBusy, setAhBusy] = useState(false)
  const [ahSyncProgress, setAhSyncProgress] = useState('')
  const [lidlWebProgress, setLidlWebProgress] = useState('')
  const [lidlWindow, setLidlWindow] = useState(null)
  const [lidlFrom, setLidlFrom] = useState('')
  const [lidlTo, setLidlTo] = useState('')
  const [lidlWindowSaving, setLidlWindowSaving] = useState(false)
  const [jumboPocProgress, setJumboPocProgress] = useState('')
  const [jumboPocResult, setJumboPocResult] = useState(null)
  const [jumboImportCandidate, setJumboImportCandidate] = useState(null)
  const [jumboImportBusy, setJumboImportBusy] = useState(false)
  const [jumboFrom, setJumboFrom] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 29)
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
  })
  const [jumboTo, setJumboTo] = useState(() => {
    const d = new Date()
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
  })

  const rows = useMemo(
    () => deriveStoreConnectionRows(providers, connections, ahConnection),
    [providers, connections, ahConnection],
  )
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null
  const lidlPeriodUnsaved = Boolean(lidlWindow?.can_manage) && (
    lidlFrom !== (lidlWindow.configured_from_date || lidlWindow.from_date || '') ||
    lidlTo !== (lidlWindow.configured_to_date || '')
  )
  const lidlBookmarklet = useMemo(() => buildLidlWebBookmarklet(window.location.origin), [])
  const jumboPeriodValid = useMemo(() => {
    try {
      jumboDateWindow(jumboFrom, jumboTo)
      return true
    } catch {
      return false
    }
  }, [jumboFrom, jumboTo])
  const jumboPocBookmarklet = useMemo(
    () => jumboPeriodValid
      ? buildJumboPocBookmarklet(window.location.origin + window.location.pathname, { from_date: jumboFrom, to_date: jumboTo })
      : '',
    [jumboFrom, jumboTo, jumboPeriodValid],
  )

  const storeConnectionColumns = useMemo(() => [
    {
      key: 'providerName',
      header: 'Winkel',
      width: 180,
      renderCell: (row) => <span data-testid={`store-connection-name-${row.providerCode}`}>{row.providerName}</span>,
    },
    {
      key: 'typeLabel',
      header: 'Type koppeling',
      width: 190,
      renderCell: (row) => <span data-testid={`store-connection-type-${row.providerCode}`}>{row.typeLabel}</span>,
    },
    {
      key: 'statusLabel',
      header: 'Status',
      width: 130,
      renderCell: (row) => <span data-testid={`store-connection-status-${row.providerCode}`}>{row.statusLabel}</span>,
    },
    {
      key: 'lastSyncLabel',
      header: 'Laatste synchronisatie',
      width: 210,
      renderCell: (row) => <span data-testid={`store-connection-sync-${row.providerCode}`}>{row.lastSyncLabel}</span>,
    },
    {
      key: 'action',
      header: 'Actie',
      width: 210,
      renderCell: (row) => (
        <div>
          <Button
            type="button"
            variant={(row.connectionSource === 'ah_account' && row.statusLabel === 'gekoppeld') || row.connection ? 'secondary' : 'primary'}
            data-testid={`store-connection-action-${row.providerCode}`}
            onClick={() => handleStoreConnectionAction(row)}
            disabled={isLoading || isSaving || row.providerCode === 'aldi'}
          >
            {row.actionLabel}
          </Button>
          <div
            data-testid={`store-connection-ref-${row.providerCode}`}
            style={{ fontSize: 'var(--font-size-ui-body)', marginTop: '6px' }}
          >
            {row.cardNumber || '—'}
          </div>
        </div>
      ),
    },
  ], [isLoading, isSaving])

  async function loadAhStatus() {
    const data = await fetchJson('/api/receipts/retailers/ah/status')
    setAhConnection(data || { connected: false, persistence: 'encrypted_database' })
    return data
  }

  async function loadPageData() {
    setIsLoading(true)
    setError('')
    try {
      const householdData = await fetchJson('/api/household')
      const [providerData, connectionData] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
      ])
      setHousehold(householdData)
      setProviders(providerData)
      setConnections(connectionData)
      await loadAhStatus()
      const windowData = await fetchJson('/api/receipts/retailers/lidl/import-window')
      setLidlWindow(windowData)
      setLidlFrom(windowData.configured_from_date || windowData.from_date || '')
      setLidlTo(windowData.configured_to_date || '')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelkoppelingen konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  async function saveLidlWindow(reset = false) {
    setLidlWindowSaving(true)
    try {
      const data = await fetchJson('/api/receipts/retailers/lidl/import-window', {
        method: 'PUT',
        body: JSON.stringify({
          from_date: reset ? null : (lidlFrom || null),
          to_date: reset ? null : (lidlTo || null),
        }),
      })
      setLidlWindow(data)
      setLidlFrom(data.configured_from_date || data.from_date || '')
      setLidlTo(data.configured_to_date || '')
      showFeedback({ variant: 'success', title: 'Lidl-importperiode opgeslagen', message: reset ? 'Automatische periode hersteld.' : 'De nieuwe periode geldt bij de volgende import.' })
    } catch (err) {
      showFeedback({ variant: 'error', title: 'Lidl-importperiode', message: normalizeErrorMessage(err?.message) || 'Opslaan mislukt.' })
    } finally {
      setLidlWindowSaving(false)
    }
  }

  useEffect(() => {
    ahSyncPageMountedRef.current = true
    lidlImportPageMountedRef.current = true
    return () => {
      ahSyncPageMountedRef.current = false
      dismissFeedbackIfKey('ah-receipt-sync')
      lidlImportPageMountedRef.current = false
      dismissFeedbackIfKey('lidl-receipt-import')
    }
  }, [dismissFeedbackIfKey])

  useEffect(() => {
    loadPageData()
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const ahResult = params.get('ah')
    if (!ahResult) return
    if (ahResult === 'connected') {
      showFeedback({
        variant: 'success',
        title: 'Albert Heijn gekoppeld',
        message: 'De koppeling is veilig opgeslagen. Nieuwe digitale AH-bonnen kunnen nu rechtstreeks in Inhuis worden opgehaald.',
      })
    } else if (ahResult === 'error') {
      showFeedback({
        variant: 'error',
        title: 'Albert Heijn koppelen',
        message: 'De AH-login kon niet worden afgerond. Probeer de koppeling opnieuw.',
      })
    }
    params.delete('ah')
    const query = params.toString()
    window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash)
  }, [showFeedback])

  useEffect(() => {
    let lidlCounts = { new: 0, known: 0, refreshed: 0, failed: 0 }
    let cancelled = false
    let lidlSourceWindow = null

    async function handleMessage(event) {
      if (cancelled || event.origin !== LIDL_WEB_ORIGIN) return
      const data = event.data
      if (!data || typeof data !== 'object') return

      if (data.type === 'inhuis:lidl-handshake') {
        lidlCounts = { new: 0, known: 0, refreshed: 0, failed: 0 }
        if (Number(data.bookmarklet_version || 0) !== LIDL_BOOKMARKLET_VERSION) {
          setLidlWebProgress('Je gebruikt een oude Lidl-favoriet. Verwijder die en sleep de nieuwe Lidl-bonnen naar Inhuis v2-knop opnieuw naar je favorietenbalk.')
          showFeedback({
            key: 'lidl-receipt-import',
            variant: 'warning',
            title: 'Lidl-favoriet vernieuwen',
            message: 'De opgeslagen Lidl-favoriet is verouderd.',
            detail: 'Verwijder de oude favoriet en sleep de nieuwe v2-knop één keer opnieuw naar je favorietenbalk.',
          })
          return
        }
        lidlSourceWindow = event.source
        setLidlWebProgress('Lidl is verbonden met deze Inhuis-sessie. Bonnen worden voorbereid…')
        try {
          const period = await fetchJson('/api/receipts/retailers/lidl/import-window')
          if (cancelled) return
          setLidlWindow(period)
          setLidlWebProgress('Lidl-bonnen zoeken van ' + period.from_date + ' tot ' + period.to_date + '…')
          event.source?.postMessage({
            type: 'inhuis:lidl-script',
            script: buildLidlWebPageScript(window.location.origin, period),
          }, LIDL_WEB_ORIGIN)
        } catch (err) {
          setLidlWebProgress('Lidl-import afgebroken: importperiode kon niet worden geladen.')
          showFeedback({ variant: 'error', title: 'Lidl-importperiode', message: normalizeErrorMessage(err?.message) || 'Importperiode ophalen mislukt.' })
        }
        return
      }

      if (!lidlSourceWindow || event.source !== lidlSourceWindow) return

      if (data.type === 'inhuis:lidl-progress') {
        setLidlWebProgress(String(data.message || 'Lidl-bonnen verwerken…'))
        return
      }

      if (data.type === 'inhuis:lidl-receipt') {
        const receipt = data.receipt
        const receiptId = String(receipt?.id || '').trim()
        const products = Array.isArray(receipt?.products) ? receipt.products : []
        if (!/^\d{8,40}$/.test(receiptId) || !products.length) {
          lidlCounts.failed += 1
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: false,
            error: 'Lidl-bon bevat geen geldig bonnummer of artikelregels.',
          }, LIDL_WEB_ORIGIN)
          return
        }

        try {
          const result = await fetchJson('/api/receipts/retailers/import', {
            method: 'POST',
            body: JSON.stringify({
              schema_version: '1.0',
              provider: 'lidl',
              external_receipt_id: receiptId,
              receipt,
            }),
          })
          if (result?.refreshed_existing_receipt) lidlCounts.refreshed += 1
          else if (result?.duplicate === true) lidlCounts.known += 1
          else if (result?.duplicate === false && result?.raw_receipt_id) lidlCounts.new += 1
          else {
            // Unknown acknowledgement is not proof of a new receipt.
            lidlCounts.failed += 1
            event.source?.postMessage({
              type: 'inhuis:lidl-ack',
              receipt_id: receiptId,
              ok: false,
              error: 'Inhuis gaf geen herkenbaar importresultaat terug.',
            }, LIDL_WEB_ORIGIN)
            return
          }
          setLidlWebProgress('Lidl: ' + lidlCounts.new + ' nieuw, ' + lidlCounts.known
            + ' al bekend, ' + lidlCounts.refreshed + ' bijgewerkt, ' + lidlCounts.failed + ' mislukt.')
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: true,
          }, LIDL_WEB_ORIGIN)
        } catch (err) {
          lidlCounts.failed += 1
          const message = normalizeErrorMessage(err?.message) || 'De Lidl-bon kon niet worden geïmporteerd.'
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: false,
            error: message,
          }, LIDL_WEB_ORIGIN)
          if (lidlImportPageMountedRef.current) showFeedback({
            key: 'lidl-receipt-import', variant: 'error', title: 'Lidl-bon importeren', message,
          })
        }
        return
      }

      if (data.type === 'inhuis:lidl-complete') {
        if (data.mode === 'history' && lidlCounts.failed === 0) {
          try {
            const updated = await fetchJson('/api/receipts/retailers/lidl/complete', {
              method: 'POST',
              body: JSON.stringify({
                from_date: data.from_date,
                to_date: data.to_date,
                last_imported_date: data.last_imported_date,
              }),
            })
            setLidlWindow(updated)
          } catch (err) {
            lidlCounts.failed += 1
            showFeedback({ variant: 'warning', title: 'Lidl-importcheckpoint niet bijgewerkt',
              message: normalizeErrorMessage(err?.message) || 'De volgende synchronisatie leest deze periode opnieuw.' })
          }
        }
        const summary = 'Lidl: ' + lidlCounts.new + ' nieuw, ' + lidlCounts.known
          + ' al bekend, ' + lidlCounts.refreshed + ' bijgewerkt, ' + lidlCounts.failed + ' mislukt.'
        setLidlWebProgress(summary)
        if (!lidlImportPageMountedRef.current) return
        showFeedback({
          key: 'lidl-receipt-import',
          variant: lidlCounts.failed ? 'warning' : 'success',
          title: lidlCounts.failed ? 'Lidl-synchronisatie deels gelukt' : 'Lidl-synchronisatie afgerond',
          message: summary,
          detail: lidlCounts.new
            ? 'Alleen nieuwe bonnen zijn toegevoegd aan Kassa. Al bekende bonnen zijn niet dubbel toegevoegd.'
            : 'Er zijn geen nieuwe bonnen toegevoegd. Bekende bonnen blijven in hun bestaande verwerkingsfase.',
        })
        return
      }

      if (data.type === 'inhuis:lidl-error') {
        const message = String(data.message || 'De Lidl-webimport is mislukt.')
        setLidlWebProgress(message)
        if (lidlImportPageMountedRef.current) showFeedback({
          key: 'lidl-receipt-import', variant: 'error', title: 'Lidl-webimport', message,
        })
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      cancelled = true
      window.removeEventListener('message', handleMessage)
    }
  }, [showFeedback])


  useEffect(() => {
    const hash = String(window.location.hash || '')
    if (!hash.startsWith(JUMBO_POC_FRAGMENT_PREFIX)) return

    const encoded = hash.slice(JUMBO_POC_FRAGMENT_PREFIX.length)
    try {
      const payload = JSON.parse(decodeURIComponent(encoded))
      if (Number(payload?.version || 0) !== JUMBO_BOOKMARKLET_VERSION) {
        throw new Error('De Jumbo-favoriet is verouderd. Stel deze opnieuw in via Winkelkoppelingen.')
      }

      if (!payload?.ok) {
        const message = String(payload?.error || 'Jumbo-bonnen ophalen is mislukt.')
        setJumboPocProgress(message)
        setJumboPocResult(null)
        setJumboImportCandidate(null)
        showFeedback({ variant: 'error', title: 'Jumbo-bonnen ophalen', message })
      } else {
        const found = Number(payload?.total_results || 0)
        setJumboImportCandidate(Array.isArray(payload?.details) && payload.details.length ? payload : null)
        setJumboPocResult({
          totalResults: found,
          currentPage: Number(payload?.current_page || 0),
          firstDetail: payload?.first_detail || null,
          selectedCount: Array.isArray(payload?.details) ? payload.details.length : 0,
          details: Array.isArray(payload?.details) ? payload.details : [],
          sourceOrigin: payload?.source_origin || null,
          transport: 'url-fragment',
        })
        setJumboPocProgress(
          (payload?.details?.length || 0) > 0
            ? (payload?.details?.length || 0) + ' Jumbo-bon(nen) opgehaald. Controleer de gegevens hieronder.'
            : 'Geen kassabonnen in de gekozen periode gevonden.',
        )
        showFeedback({
          variant: 'success',
          title: 'Jumbo-bonnen opgehaald',
          message: (payload?.details?.length || 0) > 0 ? 'Je Jumbo-bonnen staan klaar om te controleren.' : 'Geen bonnen in deze periode gevonden.',
          detail: 'Bekijk de gegevens en bevestig apart als je deze bon naar Kassa wilt importeren.',
        })
      }
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'Het Jumbo-resultaat kon niet worden gelezen.'
      setJumboPocProgress(message)
      setJumboPocResult(null)
      setJumboImportCandidate(null)
      showFeedback({ variant: 'error', title: 'Jumbo-bonnen ophalen', message })
    } finally {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [showFeedback])

  async function confirmJumboImport() {
    if (!jumboImportCandidate || jumboImportBusy) return
    setJumboImportBusy(true)
    try {
      // Never use the URL fragment as an implicit instruction to write data.
      const counts = await importJumboBatch(
        jumboImportCandidate,
        async (envelope) => fetchJson('/api/receipts/retailers/import', {
          method: 'POST',
          body: JSON.stringify(envelope),
        }),
        buildJumboImportEnvelope,
      )
      const message = 'Jumbo: ' + counts.new + ' nieuw, ' + counts.known
        + ' al bekend, ' + counts.refreshed + ' bijgewerkt, ' + counts.failed + ' mislukt.'
      setJumboPocProgress(message)
      setJumboImportCandidate(null)
      setJumboPocResult(null)
      showFeedback({ variant: 'success', title: 'Jumbo kassabon', message })
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De Jumbo-bon kon niet veilig worden geïmporteerd.'
      const progress = err?.jumboProcessed != null
        ? ' (' + err.jumboProcessed + ' al verwerkt; veilig gestopt bij volgende bon.)'
        : ''
      setJumboPocProgress(message + progress)
      showFeedback({ variant: 'error', title: 'Jumbo kassabon', message: message + progress })
    } finally {
      setJumboImportBusy(false)
    }
  }

  async function startAhLogin() {
    setAhBusy(true)
    try {
      const returnTo = window.location.origin + '/instellingen/winkelkoppelingen'
      const data = await fetchJson(
        '/api/receipts/retailers/ah/connect?return_to=' + encodeURIComponent(returnTo),
      )
      if (!data?.login_url) throw new Error('AH-loginadres ontbreekt.')
      window.location.assign(data.login_url)
    } catch (err) {
      setAhBusy(false)
      showFeedback({
        variant: 'error',
        title: 'Albert Heijn koppelen',
        message: normalizeErrorMessage(err?.message) || 'De AH-login kon niet worden gestart.',
      })
    }
  }

  async function syncAhReceipts() {
    setAhBusy(true)
    setAhSyncProgress('AH-bonnen worden opgehaald en gecontroleerd…')
    try {
      const result = await fetchJson('/api/receipts/retailers/ah/sync', {
        method: 'POST',
        body: JSON.stringify({ limit: 100 }),
      })
      const found = Number(result?.receipts_found || 0)
      const processed = Number(result?.receipts_processed || 0)
      const skipped = Number(result?.receipts_skipped_known || 0)
      const failed = Number(result?.receipts_failed || 0)
      const summary = found + ' gevonden · ' + processed + ' nieuw verwerkt · ' + skipped + ' al bekend · ' + failed + ' mislukt.'
      const failedStages = new Set((Array.isArray(result?.errors) ? result.errors : [])
        .map((entry) => entry?.stage === 'details' ? 'ophalen van bondetails' : entry?.stage === 'import' ? 'verwerken in Kassa' : 'onbekende stap'))
      const failedTypes = new Set((Array.isArray(result?.errors) ? result.errors : [])
        .map((entry) => ['ValueError', 'HTTPStatusError', 'TimeoutException', 'ConnectError', 'IntegrityError'].includes(entry?.error_type) ? entry.error_type : 'overige fout'))
      const reasonLabels = {
        missing_article_lines: 'Geen artikelregels beschikbaar',
        missing_total_amount: 'Geen bruikbaar totaalbedrag',
        receipt_not_recognized: 'Bon niet als bruikbare kassabon herkend',
        inactive_source: 'Importbron niet actief',
        other_validation_failure: 'Andere validatiefout',
        detail_request_failed: 'Fout bij het ophalen van AH-details',
        other_import_failure: 'Andere importfout',
      }
      const reasons = new Set((Array.isArray(result?.errors) ? result.errors : [])
        .map((entry) => reasonLabels[entry?.reason_code] || 'Reden nog onbekend'))
      const failureDiagnosis = failed
        ? 'Fout bij: ' + [...failedStages].join(', ') + '. Type: ' + [...failedTypes].join(', ') + '. Reden: ' + [...reasons].join(', ') + '.'
        : ''
      const emptyLineDiagnostics = (Array.isArray(result?.errors) ? result.errors : [])
        .filter((entry) => entry?.reason_code === 'missing_article_lines' && entry?.structure_diagnostic)
        .map((entry) => entry.structure_diagnostic)
      const lineDiagnostic = emptyLineDiagnostics.map((item) => {
        const rawCount = Number.isInteger(item?.raw_products_count) ? item.raw_products_count : 0
        const mappedCount = Number.isInteger(item?.mapped_products_count) ? item.mapped_products_count : 0
        const discountsCount = Number.isInteger(item?.discounts_count) ? item.discounts_count : 0
        const paymentsCount = Number.isInteger(item?.payments_count) ? item.payments_count : 0
        const safeFields = new Set(['items', 'lines', 'receiptLines', 'basketItems', 'entries'])
        const alternatives = Array.isArray(item?.alternate_fields)
          ? item.alternate_fields.filter((key) => safeFields.has(key))
          : []
        const rawType = ['missing', 'list', 'null', 'other'].includes(item?.products_type) ? item.products_type : 'onbekend'
        return 'AH-structuur: products=' + rawType + ' (' + rawCount + ' ruwe regels, '
          + mappedCount + ' herkend), andere artikelvelden=' + (alternatives.join(', ') || 'geen')
          + ', kortingen=' + discountsCount + ', betalingen=' + paymentsCount + '.'
      }).join(' ')
      const failedReceiptDates = (Array.isArray(result?.errors) ? result.errors : []).map((entry) => {
        // Only accept calendar-like AH timestamps; never echo arbitrary provider data.
        const value = typeof entry?.date_time === 'string' ? entry.date_time.trim() : ''
        const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/.exec(value)
        if (!match) return 'Datum niet beschikbaar; tijd niet beschikbaar; transactietype niet beschikbaar.'
        const [, year, month, day, hour, minute] = match
        const validDate = Number(month) >= 1 && Number(month) <= 12
          && Number(day) >= 1 && Number(day) <= new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate()
        const validTime = hour === undefined || (Number(hour) <= 23 && Number(minute) <= 59)
        if (!validDate || !validTime) return 'Datum niet beschikbaar; tijd niet beschikbaar; transactietype niet beschikbaar.'
        return 'Mislukte bon van ' + day + '-' + month + '-' + year
          + (hour === undefined ? ', tijd niet beschikbaar' : ' om ' + hour + ':' + minute)
          + '; transactietype niet beschikbaar.'
      }).join(' ')
      setAhSyncProgress(summary + (failureDiagnosis ? ' ' + failureDiagnosis : '') + (lineDiagnostic ? ' ' + lineDiagnostic : '') + (failedReceiptDates ? ' ' + failedReceiptDates : ''))
      if (!ahSyncPageMountedRef.current) return
      showFeedback({
        key: 'ah-receipt-sync',
        variant: failed ? 'warning' : 'success',
        title: failed ? 'AH-synchronisatie deels gelukt' : 'AH-synchronisatie afgerond',
        message: summary,
        detail: failed
          ? failureDiagnosis + (lineDiagnostic ? ' ' + lineDiagnostic : '') + (failedReceiptDates ? ' ' + failedReceiptDates : '') + ' Mislukte bonnen worden bij een volgende synchronisatie opnieuw geprobeerd.'
          : processed ? 'De nieuwe bonnen staan nu in Kassa.' : 'Er waren geen nieuwe bonnen om te verwerken.',
      })
      await loadAhStatus()
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De AH-bonnen konden niet worden opgehaald.'
      setAhSyncProgress('AH-synchronisatie mislukt. Probeer het opnieuw.')
      if (!ahSyncPageMountedRef.current) return
      showFeedback({
        key: 'ah-receipt-sync',
        variant: 'error',
        title: 'AH-bonnen ophalen',
        message,
      })
    } finally {
      setAhBusy(false)
    }
  }

  async function disconnectAh() {
    setAhBusy(true)
    try {
      const result = await fetchJson('/api/receipts/retailers/ah/connect', { method: 'DELETE' })
      setAhConnection(result)
      showFeedback({ variant: 'success', message: 'Albert Heijn is ontkoppeld.' })
    } catch (err) {
      showFeedback({
        variant: 'error',
        message: normalizeErrorMessage(err?.message) || 'Albert Heijn kon niet worden ontkoppeld.',
      })
    } finally {
      setAhBusy(false)
    }
  }

  function openEditor(row) {
    setStatus('')
    setError('')
    setEditingCode(row.providerCode)
    setCardNumber(row.cardNumber || '')
  }

  function closeEditor() {
    setEditingCode('')
    setCardNumber('')
  }

  function handleStoreConnectionAction(row) {
    if (row?.providerCode === 'aldi') return
    if (row?.connectionSource === 'ah_account') {
      closeEditor()
      document.querySelector('[data-testid="ah-digital-receipts"]')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
      return
    }
    openEditor(row)
  }

  async function handleSave() {
    if (!editingRow || !household || editingRow.providerCode === 'aldi') return
    const trimmed = String(cardNumber || '').trim()
    if (!trimmed) {
      setError('Kaartnummer is verplicht.')
      return
    }
    setIsSaving(true)
    setError('')
    setStatus('')
    try {
      if (editingRow.connection?.id) {
        await fetchJson(`/api/store-connections/${editingRow.connection.id}`, {
          method: 'PUT',
          body: JSON.stringify({ external_account_ref: trimmed }),
        })
        setStatus(`${editingRow.providerName} is bijgewerkt.`)
      } else {
        await fetchJson('/api/store-connections', {
          method: 'POST',
          body: JSON.stringify({
            household_id: household.id,
            store_provider_code: editingRow.providerCode,
            external_account_ref: trimmed,
          }),
        })
        setStatus(`${editingRow.providerName} is gekoppeld.`)
      }
      await loadPageData()
      setEditingCode('')
      setCardNumber('')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'De winkelkoppeling kon niet worden opgeslagen.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AppShell title="Winkelkoppelingen" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="store-connections-page">
        <Card>
          <div style={{ display: 'grid', gap: '8px' }}>
            <h2 style={{ margin: 0, fontSize: '20px' }}>Winkelkoppelingen</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Koppel hier een winkel éénmalig. Daarna kun je via Kassabonnen automatisch bonnen ophalen zonder opnieuw te koppelen.
            </p>
          </div>
        </Card>

        <Card>
          <div data-testid="ah-digital-receipts" style={{ display: 'grid', gap: '12px', maxWidth: '680px' }}>
            <div>
              <h3 style={{ margin: 0 }}>Albert Heijn digitale bonnen</h3>
              <p style={{ margin: '6px 0 0', color: '#667085' }}>
                Status: <strong>{ahConnection?.connected ? 'gekoppeld' : 'niet gekoppeld'}</strong>.
                {ahConnection?.connected ? ' De koppeling blijft bewaard na een herstart.' : ''}
                {ahConnection?.last_sync_at ? <> Laatst gesynchroniseerd: <strong>{formatLastSync(ahConnection.last_sync_at)}</strong>.</> : null}
              </p>
            </div>

            {!ahConnection?.connected ? (
              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ color: '#667085' }}>
                  Je logt één keer rechtstreeks bij Albert Heijn in. Inhuis ontvangt de bevestiging automatisch; je hoeft geen code of link te kopiëren.
                </div>
                <div>
                  <Button type="button" onClick={startAhLogin} disabled={ahBusy || isLoading} data-testid="ah-connect-start">
                    {ahBusy ? 'AH-login openen…' : 'Albert Heijn koppelen'}
                  </Button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <Button type="button" onClick={syncAhReceipts} disabled={ahBusy} data-testid="ah-sync-receipts">
                  {ahBusy ? 'AH-bonnen ophalen…' : 'Nu synchroniseren'}
                </Button>
                <Button type="button" variant="secondary" onClick={disconnectAh} disabled={ahBusy} data-testid="ah-disconnect">
                  Ontkoppelen
                </Button>
              </div>
            )}
            {ahSyncProgress ? (
              <div className="rz-inline-feedback" role="status" aria-live="polite" data-testid="ah-sync-progress">
                {ahSyncProgress}
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <div data-testid="jumbo-receipt-poc" style={{ display: 'grid', gap: '12px', maxWidth: '760px' }}>
            <div>
              <h3 style={{ margin: 0 }}>Jumbo digitale kassabonnen</h3>
              <p style={{ margin: '6px 0 0' }}>
                Kies de periode en haal je kassabonnen op. Controleer de gevonden bonnen en bevestig daarna de import naar Kassa.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Input label="Vanaf" type="date" value={jumboFrom} onChange={(event) => { setJumboFrom(event.target.value); setJumboImportCandidate(null); setJumboPocResult(null) }} data-testid="jumbo-from-date" />
              <Input label="Tot en met" type="date" value={jumboTo} onChange={(event) => { setJumboTo(event.target.value); setJumboImportCandidate(null); setJumboPocResult(null) }} data-testid="jumbo-to-date" />
            </div>
            {!jumboPeriodValid ? <div role="alert">Kies een geldige begin- en einddatum voor Jumbo.</div> : null}
            <details data-testid="jumbo-bookmarklet-help">
              <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Eerste keer? Stel de Jumbo-favoriet in</summary>
              <div style={{ display: 'grid', gap: '8px', padding: '12px 0' }}>
                <div>Sleep de onderstaande knop één keer naar de favorietenbalk van je browser. Heb je al een oude Jumbo-favoriet? Vervang die eerst. Bij een gewijzigde importperiode sleep je de knop opnieuw.</div>
              <a
                href={jumboPeriodValid ? jumboPocBookmarklet : undefined}
                data-testid="jumbo-poc-bookmarklet"
                aria-disabled={!jumboPeriodValid}
                style={{
                  display: 'inline-flex',
                  width: 'fit-content',
                  minHeight: '40px',
                  alignItems: 'center',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--color-ui-primary)',
                  color: 'var(--color-ui-primary)',
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
                onClick={(event) => event.preventDefault()}
              >
                Jumbo-bonnen ophalen
              </a>
                <div>Open daarna Jumbo en klik op deze favoriet om de bonnen naar Inhuis terug te brengen.</div>
              </div>
            </details>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <a
                href={JUMBO_ORDERS_URL}
                role="button"
                className="rz-button-primary"
                style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', textDecoration: 'none' }}
                onClick={() => {
                  setJumboPocProgress('Open op Jumbo de favoriet om de kassabonnen op te halen.')
                  setJumboPocResult(null)
                  setJumboImportCandidate(null)
                }}
                data-testid="jumbo-poc-open"
              >
                Open mijn Jumbo
              </a>
            </div>

            {jumboPocProgress ? (
              <div className="rz-inline-feedback" data-testid="jumbo-poc-progress">{jumboPocProgress}</div>
            ) : null}

            {jumboPocResult ? (
              <div data-testid="jumbo-poc-result" style={{ display: 'grid', gap: '10px' }}>
                {jumboPocResult.details.length ? (
                  <>
                    <strong>Gevonden kassabonnen ({jumboPocResult.details.length})</strong>
                    {jumboPocResult.details.map((detail) => (
                      <div key={detail.transactionId} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                        <span>{detail.purchaseEndOn?.slice(0, 10) || 'Datum onbekend'} · {detail.storeName || 'Jumbo'}</span>
                        <strong>€ {typeof detail.parsed?.total === 'number' ? detail.parsed.total.toFixed(2).replace('.', ',') : 'onbekend'}</strong>
                      </div>
                    ))}
                    <div style={{ color: '#667085' }}>Controleer de bedragen. De bonnen worden pas opgeslagen nadat je de import bevestigt.</div>
                    <Button type="button" disabled={jumboImportBusy || !jumboImportCandidate} onClick={confirmJumboImport} data-testid="jumbo-confirm-import">
                      {jumboImportBusy ? 'Jumbo-bonnen verwerken…' : 'Importeer ' + jumboPocResult.selectedCount + ' bon(nen) naar Kassa'}
                    </Button>
                  </>
                ) : (
                  <div>Er zijn geen Jumbo-bonnen gevonden in de gekozen periode.</div>
                )}
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <div data-testid="lidl-digital-receipts" style={{ display: 'grid', gap: '12px', maxWidth: '760px' }}>
            <div>
              <h3 style={{ margin: 0 }}>Lidl digitale bonnen</h3>
              <p style={{ margin: '6px 0 0', color: '#667085' }}>
                Gebruik je normale Lidl.nl-login. Inhuis neemt alleen de bongegevens over; je wachtwoord, cookies en Lidl-sessie blijven in je browser.
              </p>
            </div>

            <div data-testid="lidl-import-window">
              <strong>Importperiode</strong>
              <p>{lidlWindow ? lidlWindow.from_date + ' t/m ' + lidlWindow.to_date : 'Laden…'}</p>
              {lidlPeriodUnsaved ? (
                <div className="rz-inline-feedback" role="status" data-testid="lidl-period-unsaved">
                  De gekozen importperiode is nog niet opgeslagen. Klik eerst op Opslaan.
                </div>
              ) : null}
              {lidlWindow?.can_manage ? <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <Input type="date" label="Van" value={lidlFrom} onChange={e => setLidlFrom(e.target.value)} />
                <Input type="date" label="Tot (optioneel)" value={lidlTo} onChange={e => setLidlTo(e.target.value)} />
                <Button onClick={() => saveLidlWindow(false)} disabled={lidlWindowSaving || !lidlFrom || Boolean(lidlTo && lidlFrom > lidlTo)}>Opslaan</Button>
                <Button variant="secondary" onClick={() => saveLidlWindow(true)} disabled={lidlWindowSaving}>Automatisch</Button>
              </div> : null}
            </div>
            <div style={{ display: 'grid', gap: '10px' }}>
              <div><strong>Eenmalig na deze update:</strong> verwijder eerst je oude Lidl-favoriet en sleep daarna de nieuwe v2-knop hieronder naar de favorietenbalk.</div>
              <a
                href={lidlBookmarklet}
                data-testid="lidl-web-bookmarklet"
                style={{
                  display: 'inline-flex',
                  width: 'fit-content',
                  minHeight: '40px',
                  alignItems: 'center',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--color-ui-primary)',
                  color: 'var(--color-ui-primary)',
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
                onClick={(event) => event.preventDefault()}
              >
                Lidl-bonnen naar Inhuis v2
              </a>
              <div style={{ color: '#667085' }}>
                Gebruik daarna de knop hieronder. Laat dit Inhuis-tabblad open en klik in de geopende Lidl-tab op de nieuwe v2-favoriet. Vanaf v2 blijft de favoriet zelf klein en haalt hij de actuele importcode uit je bestaande Inhuis-sessie, zodat toekomstige parserwijzigingen niet opnieuw een nieuwe favoriet vereisen.
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button
                type="button"
                onClick={() => window.open(LIDL_HISTORY_URL, 'inhuis-lidl-receipts')}
                disabled={lidlPeriodUnsaved || lidlWindowSaving || !lidlWindow}
                data-testid="lidl-web-open-history"
              >
                Open mijn Lidl-kassabonnen
              </Button>
            </div>

            {lidlWebProgress ? (
              <div className="rz-inline-feedback" data-testid="lidl-web-progress">{lidlWebProgress}</div>
            ) : null}
          </div>
        </Card>

        <Card>
          <div data-testid="aldi-digital-unavailable" role="status" style={{ display: 'grid', gap: '6px' }}>
            <h3 style={{ margin: 0 }}>Aldi en PLUS</h3>
            <p style={{ margin: 0 }}>Voor Aldi en PLUS zijn momenteel geen digitaal toegankelijke kassabonnen voor een rechtstreekse koppeling met Inhuis aangetoond. Rechtstreeks ophalen van kassabonnen is daarom momenteel niet mogelijk.</p>
            <p style={{ margin: 0 }}>Papieren kassabonnen van Aldi en PLUS kunnen nog steeds via Kassa worden gescand.</p>
          </div>
        </Card>

        <PicnicAccountResearchPanel />

        <Card>
          {error ? <div className="rz-inline-feedback" data-testid="store-connections-error">{error}</div> : null}
          {status ? <div className="rz-inline-feedback rz-inline-feedback-success" data-testid="store-connections-status">{status}</div> : null}

          <DataTable
            columns={storeConnectionColumns}
            data={rows}
            getRowKey={(row) => row.providerCode}
            emptyMessage="Geen winkels beschikbaar."
            dataTestId="store-connections-table"
            tableClassName="rz-store-review-table"
            stickyHeader={false}
            stickyFilters={false}
          />
        </Card>

        {editingRow ? (
          <Card>
            <div data-testid="store-connection-editor" style={{ display: 'grid', gap: '12px', maxWidth: '520px' }}>
              <div style={{ display: 'grid', gap: '4px' }}>
                <h3 style={{ margin: 0 }}>{editingRow.connection ? 'Winkelkoppeling wijzigen' : 'Winkel koppelen'}</h3>
                <div data-testid="store-connection-editor-provider" style={{ color: '#667085' }}>{editingRow.providerName}</div>
              </div>

              <div>
                <div className="rz-label">Type koppeling</div>
                <div data-testid="store-connection-editor-type">klantenkaart</div>
              </div>

              <Input
                label="Kaartnummer / klantnummer"
                data-testid="store-connection-card-number"
                value={cardNumber}
                onChange={(event) => setCardNumber(event.target.value)}
                disabled={isSaving}
              />

              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <Button type="button" data-testid="store-connection-save" onClick={handleSave} disabled={isSaving}>Opslaan koppeling</Button>
                <Button type="button" variant="secondary" data-testid="store-connection-cancel" onClick={closeEditor} disabled={isSaving}>Annuleren</Button>
              </div>
            </div>
          </Card>
        ) : null}
      </div>
    </AppShell>
  )
}
