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
import { deriveReceiptConnectionOverview, displayedImportDate, firstImportDate } from './receiptConnectionOverviewModel.js'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import PicnicAccountResearchPanel from './PicnicAccountResearchPanel.jsx'
import ImportProgress from './ImportProgress.jsx'
import RetailerBookmarkletHelp from './RetailerBookmarkletHelp.jsx'
import RetailerReceiptPanel from './RetailerReceiptPanel.jsx'
import './receiptConnectionCompact.css'

export default function StoreConnectionsPage() {
  const { showFeedback, dismissFeedbackIfKey } = useAppFeedback()
  const isMobileViewport = useMobileAppViewport()
  const [activeProvider, setActiveProvider] = useState('')
  const [latestImportDates, setLatestImportDates] = useState({})
  const [setupHelpStore, setSetupHelpStore] = useState('')
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
  const [ahPhase, setAhPhase] = useState('')
  const [ahCounts, setAhCounts] = useState(null)
  const [lidlWebProgress, setLidlWebProgress] = useState('')
  const [lidlPhase, setLidlPhase] = useState('')
  const [lidlCountsView, setLidlCountsView] = useState(null)
  const [lidlWindow, setLidlWindow] = useState(null)
  const [lidlFrom, setLidlFrom] = useState('')
  const [lidlTo, setLidlTo] = useState('')
  const [lidlWindowSaving, setLidlWindowSaving] = useState(false)
  const [jumboPocProgress, setJumboPocProgress] = useState('')
  const [jumboPhase, setJumboPhase] = useState('')
  const [jumboProgress, setJumboProgress] = useState(null)
  const [jumboPocResult, setJumboPocResult] = useState(null)
  const [jumboImportCandidate, setJumboImportCandidate] = useState(null)
  const [jumboImportBusy, setJumboImportBusy] = useState(false)
  const [jumboFrom, setJumboFrom] = useState(() => firstImportDate())
  const [jumboTo, setJumboTo] = useState(() => {
    const d = new Date()
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
  })

  const rows = useMemo(
    () => deriveStoreConnectionRows(providers, connections, ahConnection),
    [providers, connections, ahConnection],
  )
  const digitalReceiptRows = useMemo(() => {
    const phases = { ah: ahPhase, jumbo: jumboPhase, lidl: lidlPhase }
    const phaseLabels = {
      waiting: 'Verbinding maken', fetching: 'Bonnen ophalen',
      validating: 'Controleren', importing: 'Verwerken',
      completed: 'Afgerond', failed: 'Controle nodig',
    }
    return deriveReceiptConnectionOverview(rows, ahConnection, latestImportDates).map(row => ({
      ...row,
      statusLabel: phaseLabels[phases[row.providerCode]] || row.statusLabel,
    }))
  }, [rows, ahConnection, latestImportDates, ahPhase, jumboPhase, lidlPhase])
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null
  const lidlPeriodUnsaved = Boolean(lidlWindow) && (
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

  const receiptConnectionColumns = useMemo(() => [
    {
      key: 'providerName',
      header: 'Winkel',
      width: isMobileViewport ? 90 : 190,
      renderCell: row => <span data-testid={`receipt-connection-name-${row.providerCode}`}>{row.providerName}</span>,
    },
    {
      key: 'lastSyncLabel',
      header: 'Laatst bijgewerkt',
      width: isMobileViewport ? 115 : 180,
      renderCell: row => (
        <span
          data-testid={`receipt-connection-updated-${row.providerCode}`}
          title={row.isDefaultImportDate ? 'Nog geen bonnen verwerkt. Startdatum voor de eerste keer ophalen.' : undefined}
        >
          {row.lastSyncLabel}
        </span>
      ),
    },
    {
      key: 'action',
      header: 'Status',
      width: isMobileViewport ? 175 : 230,
      renderCell: row => (
        <span data-testid={`receipt-connection-status-${row.providerCode}`}>
          {row.providerCode === 'aldi' || row.providerCode === 'plus' ? (
            <span
              data-testid={`receipt-connection-unavailable-${row.providerCode}`}
              title="Deze winkelketen biedt geen digitale kassabonnen aan via haar website of klantenpas."
              style={{ color: 'var(--color-ui-primary)', fontWeight: 600 }}
            >Geen koppeling mogelijk</span>
          ) : (
            <Button
              type="button"
              variant={activeProvider === row.providerCode ? 'secondary' : 'primary'}
              data-testid={`receipt-connection-action-${row.providerCode}`}
              disabled={isLoading}
              onClick={() => handleReceiptConnectionAction(row)}
            >
              {row.actionLabel}
            </Button>
          )}
        </span>
      ),
    },
  ], [activeProvider, isLoading, isMobileViewport])

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

  async function refreshLatestImportDates({ resetPeriods = false } = {}) {
    const response = await fetchJson('/api/receipts/retailers/last-updated')
    const latest = response?.dates || {}
    setLatestImportDates(latest)
    if (resetPeriods) {
      setJumboFrom(displayedImportDate(latest.jumbo).day)
      setLidlFrom(displayedImportDate(latest.lidl).day)
    }
    return latest
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
      try {
        await refreshLatestImportDates({ resetPeriods: true })
      } catch {
        // A temporary read failure must not prevent using Winkelkoppelingen.
        // The previous year's first day remains the conservative initial window.
        setJumboFrom(firstImportDate())
        setLidlFrom(firstImportDate())
      }
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelkoppelingen konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  async function openLidlWithSavedPeriod() {
    if (lidlWindowSaving) return
    if (!lidlWindow || !lidlFrom || (lidlTo && lidlFrom > lidlTo)) {
      showFeedback({
        variant: 'error',
        title: 'Lidl openen',
        message: 'Kies eerst een geldige periode om je Lidl-bonnen op te halen.',
      })
      return
    }

    // Lidl's browser favorite reads the household-scoped, confirmed window.
    // Save changed dates before visiting Lidl; never run with a stale period.
    const needsSave = lidlPeriodUnsaved
    if (needsSave && !lidlWindow.can_manage) {
      showFeedback({
        variant: 'error',
        title: 'Lidl openen',
        message: 'De gekozen periode kan niet worden opgeslagen. Vraag de beheerder van je huishouden om de Lidl-periode in te stellen.',
      })
      return
    }

    // Open synchronously within the user click. An async window.open would
    // otherwise be blocked by Firefox/other browser popup protection.
    // The fresh window retains its opener reference for Lidl's existing postMessage
    // contract; it navigates to Lidl only AFTER confirmed persistence.
    let lidlTab
    try {
      lidlTab = window.open('about:blank', '_blank')
    } catch {
      lidlTab = null
    }
    if (!lidlTab) {
      showFeedback({
        variant: 'error',
        title: 'Lidl openen',
        message: 'De browser heeft het Lidl-tabblad geblokkeerd. Sta pop-ups voor Inhuis toe en probeer opnieuw.',
      })
      return
    }

    setLidlWindowSaving(true)
    try {
      // The newly opened tab stays visible while the period is saved.
      // Never expose household or receipt data in the provisional page.
      if (lidlTab.document?.body) {
        lidlTab.document.title = 'Inhuis - Lidl'
        lidlTab.document.body.textContent = 'Inhuis bereidt Lidl voor…'
      }
      if (needsSave) {
        const data = await fetchJson('/api/receipts/retailers/lidl/import-window', {
          method: 'PUT',
          body: JSON.stringify({
            from_date: lidlFrom,
            to_date: lidlTo || null,
          }),
        })
        if (
          data?.configured_from_date !== lidlFrom ||
          (data?.configured_to_date || '') !== lidlTo
        ) {
          throw new Error('Inhuis kon de gekozen importperiode niet bevestigen.')
        }
        setLidlWindow(data)
        setLidlFrom(data.configured_from_date)
        setLidlTo(data.configured_to_date || '')
      }

      if (lidlTab.closed) {
        throw new Error('Het Lidl-tabblad is gesloten voordat de periode gereed was.')
      }
      lidlTab.location.replace(LIDL_HISTORY_URL)
    } catch (err) {
      if (!lidlTab.closed) lidlTab.close()
      showFeedback({
        variant: 'error',
        title: 'Lidl openen',
        message: 'De gekozen periode kon niet worden voorbereid. Lidl is niet geopend. Probeer het opnieuw.',
        detail: normalizeErrorMessage(err?.message),
      })
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
      setActiveProvider('ah')
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
        setActiveProvider('lidl')
        lidlCounts = { new: 0, known: 0, refreshed: 0, failed: 0 }
        setLidlCountsView(null)
        setLidlPhase('waiting')
        if (Number(data.bookmarklet_version || 0) !== LIDL_BOOKMARKLET_VERSION) {
          setLidlPhase('failed')
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
        setLidlPhase('fetching')
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
          setLidlPhase('failed')
          setLidlWebProgress('Lidl-import afgebroken: importperiode kon niet worden geladen.')
          showFeedback({ variant: 'error', title: 'Lidl-importperiode', message: normalizeErrorMessage(err?.message) || 'Importperiode ophalen mislukt.' })
        }
        return
      }

      if (!lidlSourceWindow || event.source !== lidlSourceWindow) return

      if (data.type === 'inhuis:lidl-progress') {
        setLidlPhase('fetching')
        setLidlWebProgress(String(data.message || 'Lidl-bonnen verwerken…'))
        return
      }

      if (data.type === 'inhuis:lidl-receipt') {
        setLidlPhase('importing')
        const receipt = data.receipt
        const receiptId = String(receipt?.id || '').trim()
        const products = Array.isArray(receipt?.products) ? receipt.products : []
        if (!/^\d{8,40}$/.test(receiptId) || !products.length) {
          lidlCounts.failed += 1
          setLidlCountsView({ ...lidlCounts })
          setLidlPhase('failed')
          setLidlWebProgress('Lidl-bon bevat geen geldig bonnummer of artikelregels.')
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
            setLidlCountsView({ ...lidlCounts })
            setLidlPhase('failed')
            setLidlWebProgress('Inhuis gaf geen herkenbaar Lidl-importresultaat terug.')
            event.source?.postMessage({
              type: 'inhuis:lidl-ack',
              receipt_id: receiptId,
              ok: false,
              error: 'Inhuis gaf geen herkenbaar importresultaat terug.',
            }, LIDL_WEB_ORIGIN)
            return
          }
          setLidlCountsView({ ...lidlCounts })
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
          setLidlCountsView({ ...lidlCounts })
          setLidlPhase('failed')
          setLidlWebProgress(message)
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
        if (lidlCounts.failed === 0) {
          try {
            await refreshLatestImportDates({ resetPeriods: true })
          } catch {
            // Receipt results are already acknowledged; date display can retry next visit.
          }
        }
        setLidlCountsView({ ...lidlCounts })
        setLidlPhase(lidlCounts.failed ? 'failed' : 'completed')
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
        setLidlPhase('failed')
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
    setActiveProvider('jumbo')

    const encoded = hash.slice(JUMBO_POC_FRAGMENT_PREFIX.length)
    try {
      const payload = JSON.parse(decodeURIComponent(encoded))
      if (Number(payload?.version || 0) !== JUMBO_BOOKMARKLET_VERSION) {
        throw new Error('De Jumbo-favoriet is verouderd. Stel deze opnieuw in via Winkelkoppelingen.')
      }

      if (!payload?.ok) {
        const message = String(payload?.error || 'Jumbo-bonnen ophalen is mislukt.')
        setJumboPhase('failed')
        setJumboPocProgress(message)
        setJumboPocResult(null)
        setJumboImportCandidate(null)
        showFeedback({ variant: 'error', title: 'Jumbo-bonnen ophalen', message })
      } else {
        const found = Number(payload?.total_results || 0)
        setJumboImportCandidate(Array.isArray(payload?.details) && payload.details.length ? payload : null)
        setJumboPhase('validating')
        setJumboProgress(null)
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
      setJumboPhase('failed')
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
    setJumboPhase('validating')
    setJumboProgress(null)
    try {
      // Never use the URL fragment as an implicit instruction to write data.
      const counts = await importJumboBatch(
        jumboImportCandidate,
        async (envelope) => fetchJson('/api/receipts/retailers/import', {
          method: 'POST',
          body: JSON.stringify(envelope),
        }),
        buildJumboImportEnvelope,
        (progress) => {
          setJumboProgress(progress)
          setJumboPhase(progress.phase)
        },
      )
      const message = 'Jumbo: ' + counts.new + ' nieuw, ' + counts.known
        + ' al bekend, ' + counts.refreshed + ' bijgewerkt, ' + counts.failed + ' mislukt.'
      setJumboPhase('completed')
      setJumboPocProgress(message)
      setJumboImportCandidate(null)
      setJumboPocResult(null)
      try {
        await refreshLatestImportDates({ resetPeriods: true })
      } catch {
        // A display refresh must not turn a confirmed Kassa import into a failure.
      }
      showFeedback({ variant: 'success', title: 'Jumbo kassabon', message })
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De Jumbo-bon kon niet veilig worden geïmporteerd.'
      const progress = err?.jumboProcessed != null
        ? ' (' + err.jumboProcessed + ' al verwerkt; veilig gestopt bij volgende bon.)'
        : ''
      setJumboPhase('failed')
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
    setAhPhase('fetching')
    setAhCounts(null)
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
      setAhCounts({ new: processed, known: skipped, refreshed: 0, failed })
      setAhPhase(failed ? 'failed' : 'completed')
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
      setAhPhase('failed')
      setAhSyncProgress('AH-synchronisatie mislukt. ' + message)
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

  function handleReceiptConnectionAction(row) {
    if (!row) return
    setEditingCode('')
    setActiveProvider(row.providerCode)
  }

  useEffect(() => {
    if (!activeProvider) return
    document.querySelector('[data-testid="receipt-connection-details"]')?.scrollIntoView({
      behavior: 'smooth', block: 'start',
    })
  }, [activeProvider])

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
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr)',
        gap: '16px',
        width: '100%',
        maxWidth: '760px',
        minWidth: 0,
        margin: '0 auto',
      }} data-testid="store-connections-page">
        <Card>
          <div data-testid="receipt-connections-overview" style={{ display: 'grid', gap: '12px', minWidth: 0 }}>
            <h3 style={{ margin: 0 }}>Mijn winkelkoppelingen</h3>
            {error ? <div className="rz-inline-feedback" role="alert" data-testid="store-connections-error">{error}</div> : null}
            {isMobileViewport ? (
              <div className="rz-receipt-connection-mobile-heading" data-testid="receipt-connection-mobile-heading" role="group" aria-label="Kolommen winkelkoppelingen">
                <span>Winkel</span>
                <span>Laatst bijgewerkt</span>
                <span>Status</span>
              </div>
            ) : null}
            <DataTable
              columns={receiptConnectionColumns}
              data={digitalReceiptRows}
              getRowKey={row => row.providerCode}
              dataTestId="receipt-connections-overview-table"
              tableClassName="rz-store-review-table rz-receipt-connection-compact-table"
              emptyMessage="Geen winkelkoppelingen beschikbaar."
              stickyHeader={false}
              stickyFilters={false}
            />
            {activeProvider === 'ah' ? (
              <ImportProgress store="Albert Heijn" phase={ahPhase} message={ahSyncProgress}
                counts={ahCounts} testId="ah-sync-progress" />
            ) : null}
            {activeProvider === 'jumbo' ? (
              <ImportProgress store="Jumbo" phase={jumboPhase} message={jumboPocProgress}
                processed={jumboProgress?.processed} total={jumboProgress?.total}
                counts={jumboProgress?.counts} testId="jumbo-poc-progress" />
            ) : null}
            {activeProvider === 'lidl' ? (
              <ImportProgress store="Lidl" phase={lidlPhase} message={lidlWebProgress}
                counts={lidlCountsView} testId="lidl-web-progress" />
            ) : null}
          </div>
        </Card>

        {activeProvider ? <div data-testid="receipt-connection-details" /> : null}

        {activeProvider === 'ah' ? (
        <Card>
          <div data-testid="ah-digital-receipts" style={{ display: 'grid', rowGap: '12px', maxWidth: '680px' }}>
            <div>
              <h3 style={{ margin: 0 }}>Albert Heijn digitale bonnen</h3>
              <p style={{ margin: '6px 0 0', color: '#667085' }}>
                Status: <strong>{ahConnection?.connected ? 'gekoppeld' : 'niet gekoppeld'}</strong>.
                {ahConnection?.connected ? ' Inhuis haalt automatisch ongeveer ieder kwartier nieuwe AH-bonnen op.' : ''}
                {ahConnection?.last_sync_at ? <> Laatst gesynchroniseerd: <strong>{formatLastSync(ahConnection.last_sync_at)}</strong>.</> : null}
              </p>
            </div>

            {!ahConnection?.connected ? (
              <div style={{ display: 'grid', rowGap: '10px' }}>
                <div style={{ color: '#667085' }}>
                  Tik of klik op Koppelen en meld je aan bij Albert Heijn. Inhuis regelt daarna de toegang en het ophalen van nieuwe bonnen.
                </div>
                <div>
                  <Button type="button" onClick={startAhLogin} disabled={ahBusy || isLoading} data-testid="ah-connect-start">
                    {ahBusy ? 'AH-login openen…' : 'Albert Heijn koppelen'}
                  </Button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', columnGap: '12px', rowGap: '12px', flexWrap: 'wrap' }}>
                <Button type="button" onClick={syncAhReceipts} disabled={ahBusy} data-testid="ah-sync-receipts">
                  {ahBusy ? 'AH-bonnen ophalen…' : 'Nu synchroniseren'}
                </Button>
                <Button type="button" variant="secondary" onClick={disconnectAh} disabled={ahBusy} data-testid="ah-disconnect">
                  Ontkoppelen
                </Button>
              </div>
            )}

          </div>
        </Card>
        ) : null}

        {activeProvider === 'jumbo' ? (
        <Card>
          <RetailerReceiptPanel
            retailer="Jumbo"
            testId="jumbo-receipt-poc"
            isMobileViewport={isMobileViewport}
            from={jumboFrom}
            to={jumboTo}
            fromTestId="jumbo-from-date"
            toTestId="jumbo-to-date"
            onFromChange={(event) => {
              setJumboFrom(event.target.value)
              setJumboImportCandidate(null)
              setJumboPocResult(null)
            }}
            onToChange={(event) => {
              setJumboTo(event.target.value)
              setJumboImportCandidate(null)
              setJumboPocResult(null)
            }}
            openHref={JUMBO_ORDERS_URL}
            openTestId="jumbo-poc-open"
            onOpen={() => {
              setJumboPhase('waiting')
              setJumboProgress(null)
              setJumboPocProgress('Open op Jumbo de favoriet om de kassabonnen op te halen.')
              setJumboPocResult(null)
              setJumboImportCandidate(null)
            }}
            helpTestId="jumbo-help-open"
            onHelp={() => setSetupHelpStore('jumbo')}
            periodError={!jumboPeriodValid ? 'Kies een geldige begin- en einddatum voor Jumbo.' : ''}
            setupHelp={
              <RetailerBookmarkletHelp
                provider="jumbo"
                retailer="Jumbo"
                open={setupHelpStore === 'jumbo'}
                onClose={() => setSetupHelpStore('')}
                bookmarklet={jumboPocBookmarklet}
                valid={jumboPeriodValid}
                instructions={<>Gebruik daarna <strong>Open mijn Jumbo</strong> en klik op de favoriet
                  wanneer je op de website van Jumbo bent. Kies je later een andere importperiode,
                  sleep de favoriet dan opnieuw naar de favorietenbalk.</>}
              />
            }
          >
            {jumboPocResult ? (
              <div data-testid="jumbo-poc-result" style={{ display: 'grid', rowGap: '10px' }}>
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

          </RetailerReceiptPanel>
        </Card>
        ) : null}

        {activeProvider === 'lidl' ? (
        <Card>
          <RetailerReceiptPanel
            retailer="Lidl"
            testId="lidl-digital-receipts"
            dateRangeTestId="lidl-import-window"
            isMobileViewport={isMobileViewport}
            from={lidlFrom}
            to={lidlTo || lidlWindow?.to_date || ''}
            fromTestId="lidl-from-date"
            toTestId="lidl-to-date"
            onFromChange={(event) => setLidlFrom(event.target.value)}
            onToChange={(event) => setLidlTo(event.target.value)}
            datesDisabled={lidlWindowSaving || !lidlWindow?.can_manage}
            openTestId="lidl-web-open-history"
            onOpen={openLidlWithSavedPeriod}
            openDisabled={lidlWindowSaving || !lidlWindow}
            openBusy={lidlWindowSaving}
            helpTestId="lidl-help-open"
            onHelp={() => setSetupHelpStore('lidl')}
            setupHelp={
              <RetailerBookmarkletHelp
                provider="lidl"
                retailer="Lidl"
                open={setupHelpStore === 'lidl'}
                onClose={() => setSetupHelpStore('')}
                bookmarklet={lidlBookmarklet}
                instructions={<>Open daarna <strong>mijn Lidl</strong>, meld je aan bij Lidl en klik op de
                  opgeslagen favoriet. Laat het Inhuis-tabblad open terwijl Lidl de bonnen doorgeeft.</>}
              />
            }
          />
        </Card>
        ) : null}

        {(activeProvider === 'aldi' || activeProvider === 'plus') ? (
        <Card>
          <div data-testid="aldi-digital-unavailable" role="status" style={{ display: 'grid', rowGap: '6px' }}>
            <h3 style={{ margin: 0 }}>{activeProvider === 'aldi' ? 'Aldi' : 'PLUS'}</h3>
            <p style={{ margin: 0 }}>Deze winkelketen biedt geen digitale kassabonnen aan via haar website of klantenpas. Een koppeling met Inhuis is daarom niet mogelijk.</p>
            <p style={{ margin: 0 }}>Papieren kassabonnen kun je nog steeds in Kassa scannen.</p>
          </div>
        </Card>
        ) : null}

        {activeProvider === 'picnic' ? <PicnicAccountResearchPanel /> : null}


      </div>
    </AppShell>
  )
}
