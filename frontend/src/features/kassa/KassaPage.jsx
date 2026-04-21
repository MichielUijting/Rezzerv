import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { fetchJson, normalizeErrorMessage } from '../stores/storeImportShared'

const SOURCE_OPTIONS = [
  { value: 'klantkaartbron', label: 'Klantkaartbron' },
  { value: 'foto_kassabon', label: 'Foto kassabon' },
  { value: 'email_bijlage', label: 'E-mailbijlage' },
  { value: 'api_klantkaart', label: 'API klantkaart (later)' },
]

const STATUS_OPTIONS = [
  { value: 'nieuw', label: 'Nieuw' },
  { value: 'omgezet', label: 'Omgezet' },
  { value: 'controle_nodig', label: 'Controle nodig' },
]

function formatStatus(value) {
  return STATUS_OPTIONS.find((item) => item.value === value)?.label || value || 'Onbekend'
}

function formatSource(value) {
  return SOURCE_OPTIONS.find((item) => item.value === value)?.label || value || 'Onbekend'
}

function formatDateTime(value) {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('nl-NL', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return String(value)
  }
}

export default function KassaPage() {
  const [household, setHousehold] = useState(null)
  const [items, setItems] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [form, setForm] = useState({
    source_type: 'foto_kassabon',
    source_reference: '',
    status: 'nieuw',
  })

  async function loadPageData() {
    setIsLoading(true)
    setError('')
    try {
      const token = localStorage.getItem('rezzerv_token')
      const householdData = await fetchJson('/api/household', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      setHousehold(householdData)
      const intakeItems = await fetchJson(`/api/kassa-intake?householdId=${encodeURIComponent(householdData.id)}`)
      setItems(intakeItems || [])
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Kassa kon niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPageData()
  }, [])

  const sourceTiles = useMemo(() => SOURCE_OPTIONS.map((source) => ({
    ...source,
    count: items.filter((item) => item.source_type === source.value).length,
  })), [items])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!household) return
    setIsSaving(true)
    setError('')
    setStatusMessage('')
    try {
      const saved = await fetchJson('/api/kassa-intake', {
        method: 'POST',
        body: JSON.stringify({
          household_id: household.id,
          source_type: form.source_type,
          source_reference: form.source_reference,
          status: form.status,
        }),
      })
      setItems((current) => [saved, ...current.filter((item) => item.id !== saved.id)])
      setForm((current) => ({ ...current, source_reference: '' }))
      setStatusMessage('Intake-item toegevoegd aan Kassa.')
    } catch (err) {
      setError(normalizeErrorMessage(err?.message) || 'Intake-item kon niet worden opgeslagen.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AppShell title="Kassa" showExit={false}>
      <div data-testid="kassa-page">
        <ScreenCard>
          <div style={{ display: 'grid', gap: '20px' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '20px' }}>Kassa</h2>
              <p style={{ margin: '8px 0 0 0' }}>
                Verzamel hier ruwe kassabonbronnen. In deze eerste versie draait Kassa alleen om intake, bronregistratie en status.
              </p>
            </div>

            {error ? <div data-testid="kassa-error" className="rz-feedback rz-feedback-error">{error}</div> : null}
            {statusMessage ? <div data-testid="kassa-status" className="rz-feedback rz-feedback-success">{statusMessage}</div> : null}

            <div data-testid="kassa-source-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
              {sourceTiles.map((source) => (
                <div key={source.value} data-testid={`kassa-source-${source.value}`} className="rz-card" style={{ padding: '12px' }}>
                  <div style={{ fontWeight: 700 }}>{source.label}</div>
                  <div style={{ marginTop: '6px', color: '#4b5b6b' }}>{source.count} intake-item(s)</div>
                </div>
              ))}
            </div>

            <form data-testid="kassa-intake-form" onSubmit={handleSubmit} style={{ display: 'grid', gap: '12px' }}>
              <div style={{ display: 'grid', gap: '6px' }}>
                <label htmlFor="kassa-source-type">Bronsoort</label>
                <select
                  id="kassa-source-type"
                  data-testid="kassa-source-type"
                  value={form.source_type}
                  onChange={(event) => setForm((current) => ({ ...current, source_type: event.target.value }))}
                >
                  {SOURCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </div>

              <div style={{ display: 'grid', gap: '6px' }}>
                <label htmlFor="kassa-source-reference">Bronreferentie</label>
                <Input
                  id="kassa-source-reference"
                  data-testid="kassa-source-reference"
                  value={form.source_reference}
                  onChange={(event) => setForm((current) => ({ ...current, source_reference: event.target.value }))}
                  placeholder="Bijv. foto-2026-03-18 of mail-bijlage-001"
                />
              </div>

              <div style={{ display: 'grid', gap: '6px' }}>
                <label htmlFor="kassa-status-select">Status</label>
                <select
                  id="kassa-status-select"
                  data-testid="kassa-status-select"
                  value={form.status}
                  onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
                >
                  {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </div>

              <div>
                <Button data-testid="kassa-save-button" type="submit" disabled={isSaving || isLoading}>
                  {isSaving ? 'Opslaan...' : 'Intake-item toevoegen'}
                </Button>
              </div>
            </form>

            <div>
              <div style={{ fontWeight: 700, marginBottom: '8px' }}>Intake-overzicht</div>
              {isLoading ? (
                <div data-testid="kassa-loading">Kassa wordt geladen...</div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table data-testid="kassa-intake-table" className="rz-table">
                    <thead>
                      <tr>
                        <th>Bron</th>
                        <th>Referentie</th>
                        <th>Status</th>
                        <th>Aangemaakt</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.length ? items.map((item) => (
                        <tr key={item.id} data-testid={`kassa-intake-row-${item.id}`}>
                          <td>{formatSource(item.source_type)}</td>
                          <td data-testid={`kassa-intake-reference-${item.id}`}>{item.source_reference || '—'}</td>
                          <td data-testid={`kassa-intake-status-${item.id}`}>{formatStatus(item.status)}</td>
                          <td>{formatDateTime(item.created_at)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={4}>Nog geen intake-items aanwezig.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
