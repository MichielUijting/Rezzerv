import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
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
  JUMBO_WEB_ORIGIN,
  buildJumboPocBookmarklet,
  buildJumboPocPageScript,
} from './jumboReceiptPocBridge.js'

function formatLastSync(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function deriveRows(providers, connections) {
  const byCode = new Map((connections || []).map((connection) => [connection.store_provider_code, connection]))
  return (providers || []).map((provider) => {
    const connection = byCode.get(provider.code) || null
    const isLinked = !!connection && connection.connection_status === 'active'
    return {
      providerCode: provider.code,
      providerName: provider.name || provider.code,
      connection,
      statusLabel: isLinked ? 'gekoppeld' : 'niet gekoppeld',
      actionLabel: isLinked ? 'Wijzigen' : 'Koppelen',
      typeLabel: isLinked ? (connection.connection_type || 'klantenkaart') : 'klantenkaart',
      lastSyncLabel: isLinked ? formatLastSync(connection.last_sync_at || connection.linked_at) : '—',
      cardNumber: connection?.external_account_ref || '',
    }
  }).sort((a, b) => a.providerName.localeCompare(b.providerName, 'nl'))
}

export default function StoreConnectionsPage() {
  const { showFeedback } = useAppFeedback()
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [editingCode, setEditingCode] = useState('')
  const [cardNumber, setCardNumber] = useState('')
  const [ahConnection, setAhConnection] = useState({ connected: false, persistence: 'runtime_only' })
  const [ahLoginUrl, setAhLoginUrl] = useState('')
  const [ahCode, setAhCode] = useState('')
  const [ahBusy, setAhBusy] = useState(false)
  const [lidlWebProgress, setLidlWebProgress] = useState('')
  const [jumboPocProgress, setJumboPocProgress] = useState('')
  const [jumboPocResult, setJumboPocResult] = useState(null)
  const [jumboPocDiagnostics, setJumboPocDiagnostics] = useState([])
  const jumboWindowRef = useRef(null)

  const rows = useMemo(() => deriveRows(providers, connections), [providers, connections])
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null
  const lidlBookmarklet = useMemo(() => buildLidlWebBookmarklet(window.location.origin), [])
  const jumboPocBookmarklet = useMemo(() => buildJumboPocBookmarklet(window.location.origin), [])

  async function loadAhStatus() {
    const data = await fetchJson('/api/receipts/retailers/ah/status')
    setAhConnection(data || { connected: false, persistence: 'runtime_only' })
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
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelkoppelingen konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
  }, [])

  useEffect(() => {
    let importedCount = 0
    let cancelled = false
    let lidlSourceWindow = null

    async function handleMessage(event) {
      if (cancelled || event.origin !== LIDL_WEB_ORIGIN) return
      const data = event.data
      if (!data || typeof data !== 'object') return

      if (data.type === 'inhuis:lidl-handshake') {
        if (Number(data.bookmarklet_version || 0) !== LIDL_BOOKMARKLET_VERSION) {
          setLidlWebProgress('Je gebruikt een oude Lidl-favoriet. Verwijder die en sleep de nieuwe Lidl-bonnen naar Inhuis v2-knop opnieuw naar je favorietenbalk.')
          showFeedback({
            variant: 'warning',
            title: 'Lidl-favoriet vernieuwen',
            message: 'De opgeslagen Lidl-favoriet is verouderd.',
            detail: 'Verwijder de oude favoriet en sleep de nieuwe v2-knop één keer opnieuw naar je favorietenbalk.',
          })
          return
        }
        lidlSourceWindow = event.source
        setLidlWebProgress('Lidl is verbonden met deze Inhuis-sessie. Bonnen worden voorbereid…')
        event.source?.postMessage({
          type: 'inhuis:lidl-script',
          script: buildLidlWebPageScript(window.location.origin),
        }, LIDL_WEB_ORIGIN)
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
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: false,
            error: 'Lidl-bon bevat geen geldig bonnummer of artikelregels.',
          }, LIDL_WEB_ORIGIN)
          return
        }

        try {
          await fetchJson('/api/receipts/retailers/import', {
            method: 'POST',
            body: JSON.stringify({
              schema_version: '1.0',
              provider: 'lidl',
              external_receipt_id: receiptId,
              receipt,
            }),
          })
          importedCount += 1
          setLidlWebProgress(importedCount + ' Lidl-bon(nen) naar Kassa verwerkt.')
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: true,
          }, LIDL_WEB_ORIGIN)
        } catch (err) {
          const message = normalizeErrorMessage(err?.message) || 'De Lidl-bon kon niet worden geïmporteerd.'
          event.source?.postMessage({
            type: 'inhuis:lidl-ack',
            receipt_id: receiptId,
            ok: false,
            error: message,
          }, LIDL_WEB_ORIGIN)
          showFeedback({ variant: 'error', title: 'Lidl-bon importeren', message })
        }
        return
      }

      if (data.type === 'inhuis:lidl-complete') {
        const count = Number(data.count || importedCount || 0)
        setLidlWebProgress(count + ' Lidl-bon(nen) verwerkt. Open Kassa om ze te controleren.')
        showFeedback({
          variant: 'success',
          title: 'Lidl-bonnen geïmporteerd',
          message: count + ' bon(nen) via je bestaande Lidl-websessie verwerkt.',
          detail: 'De import is teruggekomen in dezelfde Inhuis-sessie. Je Lidl-wachtwoord en browsercookies zijn niet naar Inhuis gekopieerd.',
        })
        return
      }

      if (data.type === 'inhuis:lidl-error') {
        const message = String(data.message || 'De Lidl-webimport is mislukt.')
        setLidlWebProgress(message)
        showFeedback({ variant: 'error', title: 'Lidl-webimport', message })
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      cancelled = true
      window.removeEventListener('message', handleMessage)
    }
  }, [showFeedback])


  useEffect(() => {
    let cancelled = false
    let jumboSourceWindow = null

    function addDiagnostic(stage, detail = '') {
      setJumboPocDiagnostics((current) => [...current, { stage, detail }].slice(-12))
    }

    function isJumboOrigin(origin) {
      try {
        const url = new URL(origin)
        return url.protocol === 'https:' && (url.hostname === 'jumbo.com' || url.hostname.endsWith('.jumbo.com'))
      } catch {
        return false
      }
    }

    function handleJumboMessage(event) {
      if (cancelled) return
      const data = event.data
      if (!data || typeof data !== 'object') return

      if (data.type === 'inhuis:jumbo-poc-diagnostic') {
        const expectedWindow = jumboWindowRef.current
        if (!expectedWindow || event.source !== expectedWindow) return
        if (!isJumboOrigin(event.origin)) {
          addDiagnostic('DIAG', 'Bericht ontvangen van onverwachte origin: ' + String(event.origin || 'onbekend'))
          return
        }
        addDiagnostic(String(data.stage || 'DIAG'), String(data.detail || event.origin || ''))
        return
      }

      if (event.origin !== JUMBO_WEB_ORIGIN) {
        if (String(data.type || '').startsWith('inhuis:jumbo-poc-') && event.source === jumboWindowRef.current) {
          addDiagnostic('ORIGIN_MISMATCH', 'Verwacht ' + JUMBO_WEB_ORIGIN + ', ontvangen ' + String(event.origin || 'onbekend'))
        }
        return
      }

      if (data.type === 'inhuis:jumbo-poc-handshake') {
        if (Number(data.bookmarklet_version || 0) !== JUMBO_BOOKMARKLET_VERSION) {
          setJumboPocProgress('De Jumbo POC-favoriet is verouderd. Sleep de huidige knop opnieuw naar je favorietenbalk.')
          return
        }
        jumboSourceWindow = event.source
        addDiagnostic('HANDSHAKE_OK', event.origin)
        setJumboPocProgress('Jumbo is verbonden met deze Inhuis-sessie. Kassabonnen worden gecontroleerd…')
        event.source?.postMessage({
          type: 'inhuis:jumbo-poc-script',
          script: buildJumboPocPageScript(window.location.origin),
        }, JUMBO_WEB_ORIGIN)
        return
      }

      if (!jumboSourceWindow || event.source !== jumboSourceWindow) return

      if (data.type === 'inhuis:jumbo-poc-progress') {
        addDiagnostic('GRAPHQL_PROGRESS', String(data.message || ''))
        setJumboPocProgress(String(data.message || 'Jumbo POC uitvoeren…'))
        return
      }

      if (data.type === 'inhuis:jumbo-poc-result') {
        const result = data.result || {}
        setJumboPocResult(result)
        addDiagnostic('RESULT_OK', 'Bonnen: ' + String(Number(result.totalResults || result.receipts?.length || 0)))
        const found = Number(result.totalResults || result.receipts?.length || 0)
        setJumboPocProgress(
          found > 0
            ? found + ' Jumbo-kassabon(nen) gevonden; detail van de nieuwste bon is opgehaald.'
            : 'Geen (nieuwe) kassabonnen gevonden.'
        )
        showFeedback({
          variant: 'success',
          title: 'Jumbo POC geslaagd',
          message: found > 0
            ? 'De ingelogde Jumbo-websessie geeft toegang tot je digitale kassabonnen.'
            : 'Geen (nieuwe) kassabonnen gevonden.',
          detail: 'Dit is alleen een POC: er is niets naar Kassa of Voorraad geïmporteerd en Inhuis heeft geen Jumbo-wachtwoord of browsercookie overgenomen.',
        })
        return
      }

      if (data.type === 'inhuis:jumbo-poc-error') {
        const message = String(data.message || 'De Jumbo POC is mislukt.')
        addDiagnostic('RESULT_ERROR', message)
        setJumboPocProgress(message)
        setJumboPocResult(null)
        showFeedback({ variant: 'error', title: 'Jumbo POC', message })
      }
    }

    window.addEventListener('message', handleJumboMessage)
    return () => {
      cancelled = true
      window.removeEventListener('message', handleJumboMessage)
    }
  }, [showFeedback])

  async function startAhLogin() {
    setAhBusy(true)
    try {
      const data = await fetchJson('/api/receipts/retailers/ah/connect')
      setAhLoginUrl(data?.login_url || '')
      if (!data?.login_url) throw new Error('AH-loginadres ontbreekt.')
      window.open(data.login_url, '_blank', 'noopener,noreferrer')
      showFeedback({
        variant: 'info',
        title: 'Albert Heijn koppelen',
        message: 'Rond de AH-login af in het geopende venster.',
        detail: 'Kopieer daarna de appie://login-exit?code=... link of alleen de code en plak die hieronder.',
      })
    } catch (err) {
      showFeedback({
        variant: 'error',
        title: 'Albert Heijn koppelen',
        message: normalizeErrorMessage(err?.message) || 'De AH-login kon niet worden gestart.',
      })
    } finally {
      setAhBusy(false)
    }
  }

  async function completeAhLogin() {
    const value = String(ahCode || '').trim()
    if (!value) {
      showFeedback({ variant: 'warning', message: 'Plak eerst de AH-redirect of autorisatiecode.' })
      return
    }
    setAhBusy(true)
    try {
      const result = await fetchJson('/api/receipts/retailers/ah/connect', {
        method: 'POST',
        body: JSON.stringify({ code_or_redirect: value }),
      })
      setAhConnection(result)
      setAhCode('')
      showFeedback({
        variant: 'success',
        title: 'Albert Heijn gekoppeld',
        message: 'De koppeling is actief. Je kunt nu digitale AH-bonnen ophalen.',
      })
    } catch (err) {
      showFeedback({
        variant: 'error',
        title: 'Albert Heijn koppelen',
        message: normalizeErrorMessage(err?.message) || 'De AH-koppeling kon niet worden voltooid.',
      })
    } finally {
      setAhBusy(false)
    }
  }

  async function syncAhReceipts() {
    setAhBusy(true)
    try {
      const result = await fetchJson('/api/receipts/retailers/ah/sync', {
        method: 'POST',
        body: JSON.stringify({ limit: 20 }),
      })
      showFeedback({
        variant: result?.receipts_failed ? 'warning' : 'success',
        title: 'AH-bonnen opgehaald',
        message: String(Number(result?.receipts_processed || 0)) + ' van ' + String(Number(result?.receipts_found || 0)) + ' bonnen verwerkt.',
        detail: result?.receipts_failed ? String(result.receipts_failed) + ' bon(nen) konden niet worden verwerkt.' : 'De bonnen staan nu in Kassa.',
      })
      await loadAhStatus()
    } catch (err) {
      showFeedback({
        variant: 'error',
        title: 'AH-bonnen ophalen',
        message: normalizeErrorMessage(err?.message) || 'De AH-bonnen konden niet worden opgehaald.',
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
      setAhCode('')
      setAhLoginUrl('')
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

  async function handleSave() {
    if (!editingRow || !household) return
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
                De koppeling is in deze versie actief zolang Inhuis draait.
              </p>
            </div>

            {!ahConnection?.connected ? (
              <>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <Button type="button" onClick={startAhLogin} disabled={ahBusy || isLoading} data-testid="ah-connect-start">
                    Open AH-login
                  </Button>
                  {ahLoginUrl ? (
                    <Button type="button" variant="secondary" onClick={() => window.open(ahLoginUrl, '_blank', 'noopener,noreferrer')} disabled={ahBusy}>
                      AH-login opnieuw openen
                    </Button>
                  ) : null}
                </div>
                <Input
                  label="AH-redirect of autorisatiecode"
                  value={ahCode}
                  onChange={(event) => setAhCode(event.target.value)}
                  disabled={ahBusy}
                  data-testid="ah-connect-code"
                  placeholder="appie://login-exit?code=..."
                />
                <div>
                  <Button type="button" onClick={completeAhLogin} disabled={ahBusy || !String(ahCode || '').trim()} data-testid="ah-connect-complete">
                    Koppeling afronden
                  </Button>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <Button type="button" onClick={syncAhReceipts} disabled={ahBusy} data-testid="ah-sync-receipts">
                  AH-bonnen ophalen
                </Button>
                <Button type="button" variant="secondary" onClick={disconnectAh} disabled={ahBusy} data-testid="ah-disconnect">
                  Ontkoppelen
                </Button>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <div data-testid="jumbo-receipt-poc" style={{ display: 'grid', gap: '12px', maxWidth: '760px' }}>
            <div>
              <h3 style={{ margin: 0 }}>Jumbo kassabonnen – POC</h3>
              <p style={{ margin: '6px 0 0' }}>
                Deze proef controleert alleen of je eigen ingelogde Jumbo-websessie een bonnenlijst en één bon-detail kan lezen. Er wordt nog niets naar Kassa of Voorraad geschreven.
              </p>
            </div>

            <div style={{ display: 'grid', gap: '10px' }}>
              <div><strong>Eenmalig voor deze POC:</strong> sleep de knop hieronder naar je favorietenbalk.</div>
              <a
                href={jumboPocBookmarklet}
                data-testid="jumbo-poc-bookmarklet"
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
                Jumbo POC naar Inhuis
              </a>
              <div>
                Open daarna Jumbo met de knop hieronder. Log zo nodig normaal bij Jumbo in, laat dit Inhuis-tabblad open en klik in het Jumbo-tabblad op de opgeslagen Jumbo POC-favoriet.
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button
                type="button"
                onClick={() => {
                  setJumboPocDiagnostics([{ stage: 'TAB_OPEN', detail: JUMBO_ORDERS_URL }])
                  setJumboPocProgress('Jumbo is geopend. Log zo nodig in en klik daarna in het Jumbo-tabblad op de favoriet "Jumbo POC naar Inhuis".')
                  setJumboPocResult(null)
                  jumboWindowRef.current = window.open(JUMBO_ORDERS_URL, 'inhuis-jumbo-receipt-poc')
                  window.setTimeout(() => {
                    setJumboPocDiagnostics((current) => {
                      const hasBookmarkletSignal = current.some((entry) =>
                        ['BOOKMARKLET_START', 'HANDSHAKE_SENT', 'HANDSHAKE_OK', 'ORIGIN_MISMATCH'].includes(entry.stage)
                      )
                      return hasBookmarkletSignal
                        ? current
                        : [...current, {
                            stage: 'GEEN_REACTIE',
                            detail: 'Geen signaal van de Jumbo-favoriet ontvangen. Mogelijk is de favoriet niet gestart of is window.opener verloren gegaan.',
                          }].slice(-12)
                    })
                  }, 12000)
                }}
                data-testid="jumbo-poc-open"
              >
                Open mijn Jumbo
              </Button>
            </div>

            {jumboPocProgress ? (
              <div className="rz-inline-feedback" data-testid="jumbo-poc-progress">{jumboPocProgress}</div>
            ) : null}

            {jumboPocDiagnostics.length ? (
              <div data-testid="jumbo-poc-diagnostics" style={{ display: 'grid', gap: '4px' }}>
                <strong>Diagnose:</strong>
                {jumboPocDiagnostics.map((entry, index) => (
                  <div key={entry.stage + '-' + index}>
                    {entry.stage}: {entry.detail || '—'}
                  </div>
                ))}
              </div>
            ) : null}

            {jumboPocResult ? (
              <div data-testid="jumbo-poc-result" style={{ display: 'grid', gap: '8px' }}>
                <div><strong>Bonnen gevonden:</strong> {Number(jumboPocResult.totalResults || 0)}</div>
                {jumboPocResult.firstDetail ? (
                  <>
                    <div><strong>Nieuwste bon:</strong> {jumboPocResult.firstDetail.transactionId || '—'}</div>
                    <div><strong>Winkel:</strong> {jumboPocResult.firstDetail.storeName || '—'}</div>
                    <div><strong>Aankoopmoment:</strong> {jumboPocResult.firstDetail.purchaseEndOn || '—'}</div>
                    <div><strong>Bonformaat:</strong> {jumboPocResult.firstDetail.receiptImageType || '—'}</div>
                    <div>
                      <strong>Bonlayout gelezen:</strong>{' '}
                      {jumboPocResult.firstDetail.layoutProof?.hasItemsHeader && jumboPocResult.firstDetail.layoutProof?.hasTotalLine
                        ? 'JA'
                        : 'NEE'}
                    </div>
                    <div><strong>Tekstregels in detail:</strong> {Number(jumboPocResult.firstDetail.layoutProof?.textLineCount || 0)}</div>
                  </>
                ) : null}
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
          {error ? <div className="rz-inline-feedback" data-testid="store-connections-error">{error}</div> : null}
          {status ? <div className="rz-inline-feedback rz-inline-feedback-success" data-testid="store-connections-status">{status}</div> : null}

          <div style={{ overflowX: 'auto' }}>
            <table className="rz-table" data-testid="store-connections-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Winkel</th>
                  <th>Type koppeling</th>
                  <th>Status</th>
                  <th>Laatste synchronisatie</th>
                  <th>Actie</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.providerCode} data-testid={`store-connection-row-${row.providerCode}`}>
                    <td data-testid={`store-connection-name-${row.providerCode}`}>{row.providerName}</td>
                    <td data-testid={`store-connection-type-${row.providerCode}`}>{row.typeLabel}</td>
                    <td data-testid={`store-connection-status-${row.providerCode}`}>{row.statusLabel}</td>
                    <td data-testid={`store-connection-sync-${row.providerCode}`}>{row.lastSyncLabel}</td>
                    <td>
                      <Button
                        type="button"
                        variant={row.connection ? 'secondary' : 'primary'}
                        data-testid={`store-connection-action-${row.providerCode}`}
                        onClick={() => openEditor(row)}
                        disabled={isLoading || isSaving}
                      >
                        {row.actionLabel}
                      </Button>
                      <div data-testid={`store-connection-ref-${row.providerCode}`} style={{ fontSize: '12px', color: '#667085', marginTop: '6px' }}>
                        {row.cardNumber || '—'}
                      </div>
                    </td>
                  </tr>
                ))}
                {!rows.length ? (
                  <tr><td colSpan={5}>Geen winkels beschikbaar.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
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
