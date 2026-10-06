import { useEffect, useMemo, useState } from 'react'
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
import { deriveStoreConnectionRows, formatLastSync } from './storeConnectionsModel.js'

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
  const [ahConnection, setAhConnection] = useState({ connected: false, persistence: 'encrypted_database' })
  const [ahBusy, setAhBusy] = useState(false)
  const [lidlWebProgress, setLidlWebProgress] = useState('')
  const [jumboPocProgress, setJumboPocProgress] = useState('')
  const [jumboPocResult, setJumboPocResult] = useState(null)

  const rows = useMemo(
    () => deriveStoreConnectionRows(providers, connections, ahConnection),
    [providers, connections, ahConnection],
  )
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null
  const lidlBookmarklet = useMemo(() => buildLidlWebBookmarklet(window.location.origin), [])
  const jumboPocBookmarklet = useMemo(
    () => buildJumboPocBookmarklet(window.location.origin + window.location.pathname),
    [],
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
            disabled={isLoading || isSaving}
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
    const hash = String(window.location.hash || '')
    if (!hash.startsWith(JUMBO_POC_FRAGMENT_PREFIX)) return

    const encoded = hash.slice(JUMBO_POC_FRAGMENT_PREFIX.length)
    try {
      const payload = JSON.parse(decodeURIComponent(encoded))
      if (Number(payload?.version || 0) !== JUMBO_BOOKMARKLET_VERSION) {
        throw new Error('Onverwachte Jumbo POC-versie.')
      }

      if (!payload?.ok) {
        const message = String(payload?.error || 'De Jumbo redirect-POC is mislukt.')
        setJumboPocProgress(message)
        setJumboPocResult(null)
        showFeedback({ variant: 'error', title: 'Jumbo redirect-POC', message })
      } else {
        const found = Number(payload?.total_results || 0)
        setJumboPocResult({
          totalResults: found,
          currentPage: Number(payload?.current_page || 0),
          firstDetail: payload?.first_detail || null,
          sourceOrigin: payload?.source_origin || null,
          transport: 'url-fragment',
        })
        setJumboPocProgress(
          found > 0
            ? found + ' Jumbo-kassabon(nen) gevonden. De nieuwste bon is opgehaald en de bonlayout is ontleed.'
            : 'Geen (nieuwe) kassabonnen gevonden. De redirect-POC is succesvol teruggekeerd naar Inhuis.',
        )
        showFeedback({
          variant: 'success',
          title: 'Jumbo redirect-POC geslaagd',
          message: found > 0 ? 'Jumbo GraphQL, bon-detail en bonontleding werken via de redirect-POC.' : 'Jumbo GraphQL en de terugkeer naar Inhuis werken via de redirectmethode.',
          detail: 'Dit is alleen een POC: er is niets naar Kassa of Voorraad geschreven.',
        })
      }
    } catch (err) {
      const message = normalizeErrorMessage(err?.message) || 'Het Jumbo POC-resultaat kon niet worden gelezen.'
      setJumboPocProgress(message)
      setJumboPocResult(null)
      showFeedback({ variant: 'error', title: 'Jumbo redirect-POC', message })
    } finally {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [showFeedback])

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
    try {
      const result = await fetchJson('/api/receipts/retailers/ah/sync', {
        method: 'POST',
        body: JSON.stringify({ limit: 100 }),
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
                  Nu synchroniseren
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
                Deze proef bewijst of Jumbo GraphQL, bon-detail en bonontleding via de nieuwe redirectmethode werken. Er wordt niets naar Kassa of Voorraad geschreven.
              </p>
            </div>

            <div style={{ display: 'grid', gap: '10px' }}>
              <div><strong>Eenmalig voor deze redirect-POC:</strong> verwijder de oude Jumbo-favoriet en sleep de nieuwe v{JUMBO_BOOKMARKLET_VERSION}-knop hieronder naar je favorietenbalk.</div>
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
                Open daarna Jumbo in ditzelfde tabblad. Klik op de pagina Bestellingen op de opgeslagen Jumbo POC-favoriet. De favoriet leest de bonnenlijst en, als er een bon is, ook het detail van de nieuwste bon. Daarna keert hetzelfde tabblad via het URL-fragment terug naar Inhuis.
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button
                type="button"
                onClick={() => {
                  setJumboPocProgress('Jumbo Bestellingen geopend. Klik daar op de nieuwe Jumbo POC v' + JUMBO_BOOKMARKLET_VERSION + '-favoriet.')
                  setJumboPocResult(null)
                  window.location.assign(JUMBO_ORDERS_URL)
                }}
                data-testid="jumbo-poc-open"
              >
                Open mijn Jumbo
              </Button>
            </div>

            {jumboPocProgress ? (
              <div className="rz-inline-feedback" data-testid="jumbo-poc-progress">{jumboPocProgress}</div>
            ) : null}

            {jumboPocResult ? (
              <div data-testid="jumbo-poc-result" style={{ display: 'grid', gap: '8px' }}>
                <div><strong>POC transport:</strong> redirect via URL-fragment</div>
                <div><strong>Jumbo-origin:</strong> {jumboPocResult.sourceOrigin || '—'}</div>
                <div><strong>Bonnen gevonden:</strong> {Number(jumboPocResult.totalResults || 0)}</div>
                {jumboPocResult.firstDetail ? (
                  <>
                    <div><strong>Nieuwste bon-ID:</strong> {jumboPocResult.firstDetail.transactionId || '—'}</div>
                    <div><strong>Winkel:</strong> {jumboPocResult.firstDetail.storeName || '—'}</div>
                    <div><strong>Aankoopmoment:</strong> {jumboPocResult.firstDetail.purchaseEndOn || '—'}</div>
                    <div><strong>Bonformaat:</strong> {jumboPocResult.firstDetail.receiptImageType || '—'}</div>
                    <div><strong>Ontlede productregels:</strong> {Number(jumboPocResult.firstDetail.parsed?.items?.length || 0)}</div>
                    <div><strong>Statiegeldregels:</strong> {Number(jumboPocResult.firstDetail.parsed?.deposits?.length || 0)}</div>
                    <div><strong>Totaal:</strong> {jumboPocResult.firstDetail.parsed?.total ?? '—'}</div>
                    <div><strong>Betaalwijze:</strong> {jumboPocResult.firstDetail.parsed?.paymentMethod || '—'}</div>
                    <div><strong>Aantal artikelen:</strong> {jumboPocResult.firstDetail.parsed?.itemCount ?? '—'}</div>
                    {jumboPocResult.firstDetail.parsed?.parseError ? (
                      <div><strong>Parsermelding:</strong> {jumboPocResult.firstDetail.parsed.parseError}</div>
                    ) : null}
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
