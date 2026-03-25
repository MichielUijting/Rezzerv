import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
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
  const [household, setHousehold] = useState(null)
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [editingCode, setEditingCode] = useState('')
  const [cardNumber, setCardNumber] = useState('')

  const rows = useMemo(() => deriveRows(providers, connections), [providers, connections])
  const editingRow = rows.find((row) => row.providerCode === editingCode) || null

  async function loadPageData() {
    setIsLoading(true)
    setError('')
    try {
      const token = localStorage.getItem('rezzerv_token')
      const householdData = await fetchJson('/api/household', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const [providerData, connectionData] = await Promise.all([
        fetchJson('/api/store-providers'),
        fetchJson(`/api/store-connections?householdId=${encodeURIComponent(householdData.id)}`),
      ])
      setHousehold(householdData)
      setProviders(providerData)
      setConnections(connectionData)
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Winkelkoppelingen konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
  }, [])

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
