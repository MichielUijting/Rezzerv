import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared.jsx'

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

  const rows = useMemo(() => deriveRows(providers, connections), [providers, connections])
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null

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
