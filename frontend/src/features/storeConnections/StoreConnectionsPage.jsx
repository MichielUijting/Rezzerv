import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { buildUniversalRetailerBookmarklet, mobileBookmarkletSetupKeys, hasMobileBookmarkletSetup, copyRetailerBookmarklet } from './universalRetailerBookmarklet.js'
import { JUMBO_WEB_ORIGIN, buildJumboImportEnvelope } from './jumboReceiptImport.js'
import { jumboDateWindow, stageJumboBatch } from './jumboReceiptBatch.js'
import { deriveStoreConnectionRows, formatLastSync } from './storeConnectionsModel.js'
import { deriveReceiptConnectionOverview, displayedImportDate, firstImportDate, currentJumboImportPeriod } from './receiptConnectionOverviewModel.js'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import PicnicAccountResearchPanel from './PicnicAccountResearchPanel.jsx'
import ImportProgress from './ImportProgress.jsx'
import StoreOnboardingSelection from '../onboarding/StoreOnboardingSelection.jsx'
import {
  fetchStoreOnboardingProgress, saveStoreOnboardingSelection,
  saveStoreOnboardingResult, nextStoreForOnboarding, skipStoreForOnboarding,
} from '../onboarding/onboardingStoreConnections.js'
import HistoricalImportProgress from './HistoricalImportProgress.jsx'
import { hasPendingHistoryWork } from './historicalImportStatusModel.js'
import RetailerBookmarkletHelp from './RetailerBookmarkletHelp.jsx'
import { detectMobileRetailerEnvironment } from './retailerMobileEnvironment.js'
import RetailerReceiptPanel from './RetailerReceiptPanel.jsx'
import { filterOnboardingReceiptStores } from '../onboarding/onboardingStoreConnections.js'
import './receiptConnectionCompact.css'

export default function StoreConnectionsPage({ onboardingMode = false, onFinish = null }) {
  const navigate = useNavigate()
  const { showFeedback, dismissFeedbackIfKey } = useAppFeedback()
  const isMobileViewport = useMobileAppViewport()
  const mobileRetailer = detectMobileRetailerEnvironment().device !== 'desktop'
  const [activeProvider, setActiveProvider] = useState('')
  const expectedLidlWindowRef = useRef(null)
  const expectedJumboWindowRef = useRef(null)
  const [storeOnboarding, setStoreOnboarding] = useState(null)
  const [pendingStoreSelection, setPendingStoreSelection] = useState(null)
  const [storeOnboardingBusy, setStoreOnboardingBusy] = useState(false)
  const lidlOnboardingQueueIdRef = useRef(null)
  const lastStoreAttemptRef = useRef('')
  const [connectionHelpOpen, setConnectionHelpOpen] = useState(() => new URLSearchParams(window.location.search).has('ah'))
  const [latestImportDates, setLatestImportDates] = useState({})
  const [historySummary, setHistorySummary] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [setupHelpStore, setSetupHelpStore] = useState('')
  const [preparedCopy, setPreparedCopy] = useState(null)
  const jumboReturningRef = useRef(String(window.location.hash || '').startsWith(JUMBO_POC_FRAGMENT_PREFIX))
  const ahSyncPageMountedRef = useRef(false)
  const ahLoginNavigatingRef = useRef(false)
  const ahReturnOutcomeRef = useRef(null)
  const lidlImportPageMountedRef = useRef(false)
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (error) showFeedback({ variant: 'error', message: error }) }, [error, showFeedback])
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
      queued: 'Veilig ontvangen',
      completed: 'Afgerond', failed: 'Controle nodig',
    }
    const overview = deriveReceiptConnectionOverview(rows, ahConnection, latestImportDates).map(row => ({
      ...row,
      statusLabel: phaseLabels[phases[row.providerCode]] || row.statusLabel,
    }))
    return onboardingMode ? filterOnboardingReceiptStores(overview) : overview
  }, [rows, ahConnection, latestImportDates, ahPhase, jumboPhase, lidlPhase, onboardingMode])
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

  // Permanent across periods, dates and both entry routes. Desktop retains
  // its existing date-specific Jumbo bookmarklet and drag-to-favorites flow.
  const universalBookmarklet = useMemo(
    () => buildUniversalRetailerBookmarklet(window.location.origin, lidlBookmarklet),
    [lidlBookmarklet],
  )
  const setupKeys = useMemo(() => mobileBookmarkletSetupKeys(), [])
  const visibleOnboardingSelection = pendingStoreSelection ?? storeOnboarding?.selected ?? []
  const setupBrowserUrl = useMemo(() => {
    const url = new URL(window.location.pathname, window.location.origin)
    if (onboardingMode && ['jumbo', 'lidl'].includes(activeProvider)) url.searchParams.set('inhuis_setup', activeProvider)
    return url.href
  }, [activeProvider, onboardingMode])

  const receiptConnectionColumns = useMemo(() => [
    {
      key: 'providerName',
      header: 'Winkel',
      cellClassName: 'rz-receipt-store-cell',
      width: isMobileViewport ? 90 : 190,
      renderCell: row => <span data-testid={`receipt-connection-name-${row.providerCode}`}>{row.providerName}</span>,
    },
    {
      key: 'action',
      header: 'Status',
      cellClassName: 'rz-receipt-status-cell',
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
    {
      key: 'lastSyncLabel',
      header: 'Laatst bijgewerkt',
      cellClassName: 'rz-receipt-updated-cell',
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

  async function refreshHistoricalProgress() {
    setHistoryLoading(true)
    try {
      const overview = await fetchJson('/api/receipts/retailers/history-progress')
      setHistorySummary(overview)
      setHistoryError('')
    } catch {
      // Keep any last known counts; never present a failed refresh as zero.
      setHistoryError('De actuele importstatus kon niet worden opgehaald. Probeer Vernieuwen.')
    } finally {
      setHistoryLoading(false)
    }
  }

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
      if (onboardingMode) {
        const progress = await fetchStoreOnboardingProgress()
        // Keep a newer OAuth/browser result when the initial fetch races it.
        setStoreOnboarding(previous => previous ?? progress)
      }
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

  async function markOnboardingStoreResult(provider, result, queueId = null) {
    if (!onboardingMode) return
    try {
      const confirmed = await saveStoreOnboardingResult(provider, result, queueId)
      setStoreOnboarding(confirmed)
      if (result === 'success') {
        const next = ['ah', 'jumbo', 'lidl'].find(code => confirmed.selected.includes(code) && confirmed.results[code] == null)
        if (next) {
          setSetupHelpStore('')
          lastStoreAttemptRef.current = next
          setActiveProvider(next)
        } else {
          setActiveProvider('')
          if (confirmed.selected.every(code => confirmed.results[code] === 'success')) onFinish?.()
        }
      }
    } catch (err) {
      showFeedback({
        variant: 'error', title: 'Winkelonboarding',
        message: normalizeErrorMessage(err?.message) || 'Het winkelresultaat kon niet worden bevestigd.',
      })
    }
  }

  // Checkbox clicks never call the backend, open a browser or navigate.
  function chooseOnboardingStore(provider, checked) {
    if (!storeOnboarding?.available || storeOnboardingBusy ||
        storeOnboarding.results?.[provider] === 'success') return
    setPendingStoreSelection(previous => {
      const current = previous ?? storeOnboarding.selected
      return ['ah', 'jumbo', 'lidl'].filter(code =>
        code === provider ? checked : current.includes(code))
    })
  }

  async function skipCurrentOnboardingStore(provider) {
    if (!onboardingMode || !storeOnboarding?.available || storeOnboardingBusy) return
    setStoreOnboardingBusy(true)
    try {
      const confirmed = await saveStoreOnboardingSelection(skipStoreForOnboarding(storeOnboarding.selected, provider))
      setStoreOnboarding(confirmed)
      setSetupHelpStore('')
      const next = nextStoreForOnboarding(confirmed.selected, confirmed.results, provider)
      if (next) {
        lastStoreAttemptRef.current = provider
        setActiveProvider(next)
      } else {
        setActiveProvider('')
        onFinish?.()
      }
    } catch (err) {
      showFeedback({ variant: 'error', title: 'Winkel overslaan',
        message: normalizeErrorMessage(err?.message) || 'De keuze kon niet worden opgeslagen.' })
    } finally {
      setStoreOnboardingBusy(false)
    }
  }

  // A browser launch from a standalone PWA may require the normal browser.
  // Resume only a selected, unfinished store, never a connection result.
  useEffect(() => {
    if (!onboardingMode || isLoading || !storeOnboarding?.available) return
    const url = new URL(window.location.href)
    const provider = url.searchParams.get('inhuis_setup')
    if (!provider) return
    url.searchParams.delete('inhuis_setup')
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
    if (['jumbo', 'lidl'].includes(provider) && storeOnboarding.selected.includes(provider) &&
        storeOnboarding.results[provider] !== 'success') setActiveProvider(provider)
  }, [onboardingMode, isLoading, storeOnboarding])

  // No second start screen after selecting stores. Do not cover a returned
  // Jumbo import preview with the installation guide.
  useEffect(() => {
    if (onboardingMode && mobileRetailer && (activeProvider === 'jumbo' || activeProvider === 'lidl') &&
        !(activeProvider === 'jumbo' && jumboReturningRef.current)) {
      setSetupHelpStore(activeProvider)
    }
  }, [activeProvider, onboardingMode, mobileRetailer])

  function launchConfirmedOnboardingStore(confirmed, preparedPromise = null) {
    const code = nextStoreForOnboarding(
      confirmed.selected, confirmed.results, lastStoreAttemptRef.current,
    )
    if (!code) return
    lastStoreAttemptRef.current = code
    if (code === 'ah') {
      if (ahConnection?.connected === true) {
        void markOnboardingStoreResult('ah', 'success')
      } else {
        void startAhLogin()
      }
      return
    }
    jumboReturningRef.current = false
    if (mobileRetailer) {
      const value = universalBookmarklet
      if (value && !hasMobileBookmarkletSetup(setupKeys[code])) {
        setPreparedCopy(preparedPromise ? { value, promise: preparedPromise } : null)
      } else setPreparedCopy(null)
      setSetupHelpStore(code)
    }
    setActiveProvider(code)
  }

  async function startOnboardingStore() {
    if (!storeOnboarding?.available || storeOnboardingBusy) return
    const selected = visibleOnboardingSelection
    const code = nextStoreForOnboarding(selected, storeOnboarding.results, lastStoreAttemptRef.current)
    if (!code) return
    // Clipboard activation runs during the click, not after an awaited PUT.
    // Copying only prepares a favorite: it never starts retailer login/import.
    const preparedPromise = mobileRetailer && ['jumbo', 'lidl'].includes(code) &&
      !hasMobileBookmarkletSetup(setupKeys[code])
      ? copyRetailerBookmarklet(universalBookmarklet) : null
    setStoreOnboardingBusy(true)
    try {
      const confirmed = await saveStoreOnboardingSelection(selected)
      setStoreOnboarding(confirmed)
      setPendingStoreSelection(null)
      launchConfirmedOnboardingStore(confirmed, preparedPromise)
    } catch (err) {
      // Retain every local checkbox for an explicit retry of the same selection.
      showFeedback({
        variant: 'error', title: 'Winkelkeuze',
        message: normalizeErrorMessage(err?.message) || 'De winkelkeuze kon niet worden bewaard. Probeer opnieuw.',
      })
    } finally {
      setStoreOnboardingBusy(false)
    }
  }

  // Open the retailer window synchronously within its user click. Jumbo's
  // favorite will request a fresh window from THIS authenticated opener.
  function openJumboFromInhuis() {
    if (!mobileRetailer) {
      window.location.assign(JUMBO_ORDERS_URL)
      return true
    }
    let tab = null
    try { tab = window.open('about:blank', '_blank') } catch { /* blocked */ }
    if (!tab) {
      showFeedback({
        variant: 'error', title: 'Jumbo openen',
        message: 'De browser heeft het Jumbo-tabblad geblokkeerd. Sta pop-ups voor Inhuis toe en probeer opnieuw.',
      })
      return false
    }
    expectedJumboWindowRef.current = tab
    try {
      if (tab.document?.body) {
        tab.document.title = 'Inhuis - Jumbo'
        tab.document.body.textContent = 'Openen van Jumbo…'
      }
      tab.location.replace(JUMBO_ORDERS_URL)
      return true
    } catch {
      expectedJumboWindowRef.current = null
      try { tab.close() } catch { /* noop */ }
      showFeedback({ variant: 'error', title: 'Jumbo openen', message: 'Jumbo kon niet veilig worden geopend.' })
      return false
    }
  }

  async function openLidlWithSavedPeriod() {
    if (lidlWindowSaving) return
    if (!lidlWindow || !lidlFrom || (lidlTo && lidlFrom > lidlTo)) {
      if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
      if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
      if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
      expectedLidlWindowRef.current = lidlTab
      lidlTab.location.replace(LIDL_HISTORY_URL)
      return true
    } catch (err) {
      if (!lidlTab.closed) lidlTab.close()
      if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
    void refreshHistoricalProgress()
  }, [])

  // Android can leave the Inhuis page alive while opening AH in a browser tab.
  // Coming back must not preserve the 'AH-login openen…' busy state forever.
  // Only the household-scoped status endpoint can confirm a real connection.
  useEffect(() => {
    function resumeAhLogin() {
      if (!ahLoginNavigatingRef.current || document.visibilityState === 'hidden') return
      ahLoginNavigatingRef.current = false
      setAhBusy(false)
      void loadAhStatus().then((confirmation) => {
        if (onboardingMode && confirmation?.connected === true) {
          void markOnboardingStoreResult('ah', 'success')
        }
      }).catch(() => {
        showFeedback({
          variant: 'warning',
          title: 'Albert Heijn koppelen',
          message: 'De AH-koppelstatus kon niet worden gecontroleerd. Vernieuw Winkelkoppelingen.',
        })
      })
    }
    window.addEventListener('pageshow', resumeAhLogin)
    window.addEventListener('focus', resumeAhLogin)
    document.addEventListener('visibilitychange', resumeAhLogin)
    return () => {
      window.removeEventListener('pageshow', resumeAhLogin)
      window.removeEventListener('focus', resumeAhLogin)
      document.removeEventListener('visibilitychange', resumeAhLogin)
    }
  }, [showFeedback])

  const pendingHistoryWork = hasPendingHistoryWork(historySummary)
  useEffect(() => {
    if (!pendingHistoryWork) return undefined
    const timer = window.setInterval(() => { void refreshHistoricalProgress() }, 10000)
    return () => window.clearInterval(timer)
  }, [pendingHistoryWork])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const fromUrl = params.get('ah')
    if (fromUrl) {
      // Retain this one-time outcome across React StrictMode effect replays.
      ahReturnOutcomeRef.current = fromUrl
      params.delete('ah')
      const query = params.toString()
      window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash)
    }
    const ahResult = ahReturnOutcomeRef.current
    if (ahResult !== 'connected' && ahResult !== 'error') return

    // A redirect query only reports a browser outcome, not an established AH
    // connection. Check the household-scoped backend before claiming success.
    let cancelled = false
    async function confirmAhLogin() {
      try {
        const confirmation = await loadAhStatus()
        if (cancelled) return
        ahReturnOutcomeRef.current = null
        if (confirmation?.connected === true) {
          if (onboardingMode) await markOnboardingStoreResult('ah', 'success')
          else setActiveProvider('ah')
          if (onboardingMode) return
          showFeedback({
            variant: 'success',
            title: 'Albert Heijn gekoppeld',
            message: 'De koppeling is veilig opgeslagen. Nieuwe digitale AH-bonnen kunnen nu rechtstreeks in Inhuis worden opgehaald.',
          })
        } else {
          if (onboardingMode) await markOnboardingStoreResult('ah', 'failed')
          showFeedback({
            variant: 'error',
            title: 'Albert Heijn koppelen',
            message: 'De AH-login is niet voltooid of verlopen. Probeer de koppeling opnieuw.',
          })
        }
      } catch {
        if (!cancelled) {
          ahReturnOutcomeRef.current = null
          showFeedback({
            variant: 'warning',
            title: 'Albert Heijn koppelen',
            message: 'De AH-koppelstatus kon niet worden gecontroleerd. Vernieuw Winkelkoppelingen.',
          })
        }
      }
    }
    void confirmAhLogin()
    return () => { cancelled = true }
  }, [showFeedback])

  useEffect(() => {
    let lidlCounts = { queued: 0, failed: 0 }
    let cancelled = false
    let lidlSourceWindow = null

    async function handleMessage(event) {
      if (cancelled || event.origin !== LIDL_WEB_ORIGIN) return
      const data = event.data
      if (!data || typeof data !== 'object') return

      if (data.type === 'inhuis:lidl-handshake') {
        if (onboardingMode && (!expectedLidlWindowRef.current || event.source !== expectedLidlWindowRef.current)) return
        lidlOnboardingQueueIdRef.current = null
        setSetupHelpStore('')
        setActiveProvider('lidl')
        lidlCounts = { queued: 0, failed: 0 }
        setLidlCountsView(null)
        setLidlPhase('waiting')
        if (Number(data.bookmarklet_version || 0) !== LIDL_BOOKMARKLET_VERSION) {
          setLidlPhase('failed')
          if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
          if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
          if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
          const result = await fetchJson('/api/receipts/retailers/import-queue', {
            method: 'POST',
            body: JSON.stringify([{
              schema_version: '1.0',
              provider: 'lidl',
              external_receipt_id: receiptId,
              receipt,
            }]),
          })
          if (result?.received !== 1 || result?.import_completed !== false ||
              result?.items?.length !== 1 || !result.items[0]?.queue_id ||
              !['pending', 'processing', 'completed', 'review_required'].includes(result.items[0]?.status)) {
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
          lidlCounts.queued += 1
          lidlOnboardingQueueIdRef.current = result.items[0].queue_id
          setLidlCountsView({ ...lidlCounts })
          setLidlWebProgress('Lidl: ' + lidlCounts.queued
            + ' bonnen veilig ontvangen; verwerking in Kassa volgt automatisch.')
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
        // The old import-window checkpoint means *processed*, not merely queued.
        // Do not advance it until the worker has confirmed completion.
        if (data.mode === 'history' && lidlCounts.failed === 0 && lidlCounts.queued === 0) {
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
        if (lidlCounts.failed === 0 && lidlCounts.queued === 0) {
          try {
            await refreshLatestImportDates({ resetPeriods: true })
          } catch {
            // Receipt results are already acknowledged; date display can retry next visit.
          }
        }
        setLidlCountsView({ ...lidlCounts })
        void refreshHistoricalProgress()
        setLidlPhase(lidlCounts.failed ? 'failed' : lidlCounts.queued ? 'queued' : 'completed')
        if (onboardingMode) {
          if (lidlCounts.failed) {
            await markOnboardingStoreResult('lidl', 'failed')
          } else if (lidlCounts.queued > 0 && lidlOnboardingQueueIdRef.current) {
            await markOnboardingStoreResult('lidl', 'success', lidlOnboardingQueueIdRef.current)
          }
        }
        const summary = 'Lidl: ' + lidlCounts.queued
          + ' bonnen veilig ontvangen, ' + lidlCounts.failed
          + ' mislukt. Inhuis verwerkt ontvangen bonnen automatisch zodra onderhoud dit toestaat.'
        setLidlWebProgress(summary)
        if (!lidlImportPageMountedRef.current) return
        showFeedback({
          key: 'lidl-receipt-import',
          variant: lidlCounts.failed ? 'warning' : 'success',
          title: lidlCounts.failed ? 'Lidl-synchronisatie deels gelukt' : 'Lidl-bonnen ontvangen',
          message: summary,
          detail: 'Veilig ontvangen betekent nog niet dat de bonnen in Kassa zijn verwerkt. De datum Laatst bijgewerkt wordt niet voortijdig doorgeschoven.',
        })
        return
      }

      if (data.type === 'inhuis:lidl-error') {
        if (onboardingMode) void markOnboardingStoreResult('lidl', 'failed')
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
    jumboReturningRef.current = true
    setSetupHelpStore('')
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
        if (onboardingMode) void markOnboardingStoreResult('jumbo', 'failed')
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
      if (onboardingMode) void markOnboardingStoreResult('jumbo', 'failed')
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
      const queued = await stageJumboBatch(
        jumboImportCandidate,
        async (envelopes) => fetchJson('/api/receipts/retailers/import-queue', {
          method: 'POST',
          body: JSON.stringify(envelopes),
        }),
        buildJumboImportEnvelope,
      )
      const message = 'Jumbo: ' + queued.length + ' bonnen veilig ontvangen. Inhuis verwerkt ze '
        + 'automatisch zodra onderhoud dat toestaat. Dit is nog geen bevestiging van verwerking in Kassa.'
      setJumboProgress(null)
      setJumboPhase('queued')
      if (onboardingMode && queued.length > 0) {
        await markOnboardingStoreResult('jumbo', 'success', queued[0].queue_id)
      }
      void refreshHistoricalProgress()
      setJumboPocProgress(message)
      setJumboImportCandidate(null)
      setJumboPocResult(null)
      showFeedback({ variant: 'success', title: 'Jumbo-bonnen ontvangen', message })
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'De Jumbo-bon kon niet veilig worden geïmporteerd.'
      const progress = err?.jumboProcessed != null
        ? ' (' + err.jumboProcessed + ' al verwerkt; veilig gestopt bij volgende bon.)'
        : ''
      setJumboPhase('failed')
      if (onboardingMode) await markOnboardingStoreResult('jumbo', 'failed')
      setJumboPocProgress(message + progress)
      showFeedback({ variant: 'error', title: 'Jumbo kassabon', message: message + progress })
    } finally {
      setJumboImportBusy(false)
    }
  }

  async function startAhLogin() {
    setAhBusy(true)
    try {
      const returnTo = window.location.origin + (onboardingMode ? '/onboarding/winkels' : '/instellingen/winkelkoppelingen')
      const data = await fetchJson(
        '/api/receipts/retailers/ah/connect?return_to=' + encodeURIComponent(returnTo) + (onboardingMode ? '&onboarding=true' : ''),
      )
      if (!data?.login_url) throw new Error('AH-loginadres ontbreekt.')
      ahLoginNavigatingRef.current = true
      window.location.assign(data.login_url)
    } catch (err) {
      ahLoginNavigatingRef.current = false
      setAhBusy(false)
      if (onboardingMode) await markOnboardingStoreResult('ah', 'failed')
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
      await refreshHistoricalProgress()
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
    if (!activeProvider || onboardingMode) return
    document.querySelector('[data-testid="receipt-connection-details"]')?.scrollIntoView({
      behavior: 'smooth', block: 'start',
    })
  }, [activeProvider, onboardingMode])

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

  function finishGuidance() {
    onFinish?.()
  }

  return (
    <AppShell title={onboardingMode ? 'Winkels aansluiten' : 'Winkelkoppelingen'} showExit={false}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr)',
        gap: '16px',
        width: '100%',
        maxWidth: '760px',
        minWidth: 0,
        margin: '0 auto',
      }} data-testid="store-connections-page" data-onboarding={onboardingMode ? "true" : undefined}>
        {!onboardingMode ? (
          <Card>
            <details data-testid="store-connections-help" open={connectionHelpOpen}
              onToggle={(event) => setConnectionHelpOpen(event.currentTarget.open)}>
              <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Uitleg: winkels koppelen en bonnen ophalen</summary>
              <div style={{ display: 'grid', rowGap: '8px', marginTop: '10px' }}>
                <p style={{ margin: 0 }}>1. Kies een winkel in het overzicht. Albert Heijn vraagt om een
                  aanmelding bij Mijn AH; daarna keer je terug naar Winkelkoppelingen.
                  Lidl en Jumbo gebruiken op je telefoon een apart in te stellen bladwijzerscript. Volg de mobiele stappen om de bonnen daadwerkelijk op te halen.</p>
                <p style={{ margin: 0 }}>2. Controleer of AH gekoppeld is en tik op Nu synchroniseren als je
                  bonnen wilt ophalen. Geen gevonden bonnen kan correct zijn. Historische aankopen
                  toont opgeslagen bonrecords en verwerkingen, niet het totaal bij de winkel.</p>
                <p style={{ margin: 0 }}>3. Inhuis kun je via Terug of het dashboard verder gebruiken.
                  Boodschappen, Kassa en Voorraad vind je via de actiebalk;
                  onder Meer staan andere functies en Instellingen.</p>
                <div>
                  <Button type="button" variant="secondary" onClick={() => navigate('/home')}
                    data-testid="store-connections-guide-dashboard">
                    Bekijk dashboard
                  </Button>
                </div>
              </div>
            </details>
          </Card>
        ) : null}
        {onboardingMode ? (
          storeOnboarding?.available ? (
            <StoreOnboardingSelection
              selected={storeOnboarding.selected}
              results={storeOnboarding.results}
              busy={storeOnboardingBusy || isLoading || ahBusy || jumboImportBusy || lidlWindowSaving}
              onSelect={chooseOnboardingStore}
              onStart={startOnboardingStore}
              onRetry={startOnboardingStore}
              onLater={finishGuidance}
            />
          ) : (
            <Card>
              <p data-testid="store-onboarding-unavailable">
                {isLoading ? 'Winkelkeuze laden…' : 'De eerste winkelonboarding is niet actief voor dit huishouden. Winkels kun je via Instellingen koppelen.'}
              </p>
              <Button type="button" variant="secondary" onClick={finishGuidance}>Naar dashboard</Button>
            </Card>
          )
        ) : null}
        {!onboardingMode ? <Card>
          <div data-testid="receipt-connections-overview" style={{ display: 'grid', gap: '12px', minWidth: 0 }}>
            <h3 style={{ margin: 0 }}>Mijn winkelkoppelingen</h3>

            {isMobileViewport ? (
              <div className="rz-receipt-connection-mobile-heading" data-testid="receipt-connection-mobile-heading" role="group" aria-label="Kolommen winkelkoppelingen">
                <span>Winkel</span>
                <span>Status</span>
                <span>Laatst bijgewerkt</span>
              </div>
            ) : null}
            <DataTable
              columns={receiptConnectionColumns}
              data={digitalReceiptRows}
              getRowKey={row => row.providerCode}
              dataTestId="receipt-connections-overview-table"
              tableClassName="rz-store-review-table rz-receipt-connection-compact-table"
              wrapperClassName={isMobileViewport ? 'rz-receipt-connections-mobile' : ''}
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
        </Card> : null}

        {!onboardingMode ? <Card>
          <HistoricalImportProgress
            summary={historySummary}
            loading={historyLoading}
            error={historyError}
            onRefresh={refreshHistoricalProgress}
          />
        </Card> : null}

        {activeProvider ? <div data-testid="receipt-connection-details" /> : null}

        {activeProvider === 'ah' && !onboardingMode ? (
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
                universalBookmarklet={onboardingMode ? universalBookmarklet : ''}
                setupKeys={setupKeys}
                preparedCopy={onboardingMode ? preparedCopy : null}
                browserUrl={setupBrowserUrl}
                valid={jumboPeriodValid}
                onOpenStore={() => { setSetupHelpStore(''); window.location.assign(JUMBO_ORDERS_URL) }}
                onSkip={onboardingMode ? () => { void skipCurrentOnboardingStore('jumbo') } : null}
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
                universalBookmarklet={onboardingMode ? universalBookmarklet : ''}
                setupKeys={setupKeys}
                preparedCopy={onboardingMode ? preparedCopy : null}
                browserUrl={setupBrowserUrl}
                onOpenStore={() => { void openLidlWithSavedPeriod().then(opened => { if (opened) setSetupHelpStore('') }) }}
                onSkip={onboardingMode ? () => { void skipCurrentOnboardingStore('lidl') } : null}
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

        {onboardingMode && activeProvider ? (
          <div className="rz-store-onboarding-actions">
            <Button type="button" variant="secondary"
              data-testid="onboarding-stores-back"
              onClick={() => setActiveProvider('')}
              disabled={ahBusy || jumboImportBusy || lidlWindowSaving}>
              Winkelkeuze
            </Button>
          </div>
        ) : null}



      </div>
    </AppShell>
  )
}
