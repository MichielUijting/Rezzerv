import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Tabs from '../../ui/Tabs'
import Input from '../../ui/Input'
import Button from '../../ui/Button'
import ReceiptItemsOverview from './ReceiptItemsOverview'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './externalDatabases.css'

const TAB_LABELS = {
  overzicht: 'Overzicht',
  test: 'Test algoritme',
  winkelketens: 'Winkelketens',
}

function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function StatusBadge({ status }) {
  const label = status || 'onbekend'
  return <span className="rz-inline-feedback rz-external-databases-status">{label}</span>
}

function OverviewTile({ title, value, helper }) {
  return (
    <div className="rz-external-databases-summary-card">
      <div className="rz-external-databases-summary-label">{title}</div>
      <div className="rz-external-databases-summary-value">{value}</div>
      {helper ? <div className="rz-external-databases-summary-helper">{helper}</div> : null}
    </div>
  )
}

function ErrorOverlay({ message, onClose }) {
  if (!message) return null
  return (
    <div className="rz-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="external-databases-error-title">
      <div className="rz-modal-card">
        <h3 id="external-databases-error-title" className="rz-modal-title">Melding</h3>
        <p className="rz-modal-text">{message}</p>
        <div className="rz-modal-actions">
          <Button type="button" onClick={onClose}>Sluiten</Button>
        </div>
      </div>
    </div>
  )
}

export default function ExternalDatabasesPage() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState(TAB_LABELS.overzicht)
  const [summary, setSummary] = useState(null)
  const [retailers, setRetailers] = useState([])
  const [receiptLineText, setReceiptLineText] = useState('Mexicaanse kruidenm.')
  const [selectedRetailer, setSelectedRetailer] = useState('lidl')
  const [matchResult, setMatchResult] = useState(null)
  const [saveResult, setSaveResult] = useState(null)
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [isTesting, setIsTesting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadConfiguration() {
      setIsLoadingConfig(true)
      setError('')
      try {
        const [summaryResponse, retailersResponse] = await Promise.all([
          fetchJsonWithAuth('/api/external-databases/summary', { method: 'GET' }),
          fetchJsonWithAuth('/api/external-databases/retailers', { method: 'GET' }),
        ])
        const summaryData = await summaryResponse.json().catch(() => ({}))
        const retailersData = await retailersResponse.json().catch(() => ({}))
        if (!summaryResponse.ok) throw new Error(summaryData?.detail || 'Overzicht Externe databases kon niet worden geladen')
        if (!retailersResponse.ok) throw new Error(retailersData?.detail || 'Winkelketens konden niet worden geladen')
        if (!cancelled) {
          setSummary(summaryData)
          const nextRetailers = Array.isArray(retailersData?.retailers) ? retailersData.retailers : []
          setRetailers(nextRetailers)
          const firstRetailerCode = nextRetailers?.[0]?.retailer_code
          if (firstRetailerCode) setSelectedRetailer(firstRetailerCode)
        }
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Externe databases konden niet worden geladen')
      } finally {
        if (!cancelled) setIsLoadingConfig(false)
      }
    }

    loadConfiguration()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedRetailerConfig = useMemo(
    () => retailers.find((retailer) => retailer.retailer_code === selectedRetailer) || retailers[0] || null,
    [retailers, selectedRetailer]
  )

  async function testCandidateMatch(event) {
    event.preventDefault()
    const normalizedLine = receiptLineText.trim()
    if (!normalizedLine) {
      setError('Vul eerst een bonregel in')
      return
    }
    setIsTesting(true)
    setError('')
    setSaveResult(null)
    setMatchResult(null)
    try {
      const response = await fetchJsonWithAuth(`/api/external-databases/retailers/${encodeURIComponent(selectedRetailer)}/match-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_line_text: normalizedLine, include_below_threshold: false }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Matchpreview kon niet worden uitgevoerd')
      setMatchResult(data)
    } catch (err) {
      setError(err?.message || 'Matchpreview kon niet worden uitgevoerd')
    } finally {
      setIsTesting(false)
    }
  }

  async function saveCandidateMatches() {
    const normalizedLine = receiptLineText.trim()
    if (!normalizedLine) {
      setError('Vul eerst een bonregel in')
      return
    }
    setIsSaving(true)
    setError('')
    setSaveResult(null)
    try {
      const response = await fetchJsonWithAuth(`/api/external-databases/retailers/${encodeURIComponent(selectedRetailer)}/save-candidates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_line_text: normalizedLine, include_below_threshold: false }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Kandidaten opslaan is mislukt')
      setSaveResult(data)
    } catch (err) {
      setError(err?.message || 'Kandidaten opslaan is mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  const candidates = Array.isArray(matchResult?.candidates) ? matchResult.candidates : []
  const tabs = [TAB_LABELS.overzicht, TAB_LABELS.test, TAB_LABELS.winkelketens]

  function renderTabContent(tab) {
    if (tab === TAB_LABELS.overzicht) {
      return (
        <div className="rz-external-databases-overview">
          {isLoadingConfig ? <div>Externe databases worden geladen...</div> : null}
          <ReceiptItemsOverview onError={setError} onMessage={setError} />
        </div>
      )
    }

    if (tab === TAB_LABELS.test) {
      return (
        <div className="rz-external-databases-test">
          <form onSubmit={testCandidateMatch} className="rz-external-databases-form">
            <div className="rz-external-databases-form-grid">
              <label className="rz-input-field">
                <div className="rz-label">Winkelketen</div>
                <select className="rz-input" value={selectedRetailer} onChange={(event) => setSelectedRetailer(event.target.value)}>
                  {retailers.map((retailer) => (
                    <option key={retailer.retailer_code} value={retailer.retailer_code}>
                      {retailer.retailer_name}
                    </option>
                  ))}
                </select>
              </label>
              <Input label="Bonregel" value={receiptLineText} onChange={(event) => setReceiptLineText(event.target.value)} placeholder="Bijvoorbeeld: Mexicaanse kruidenm." />
            </div>
            <div className="rz-external-databases-actions">
              <Button type="submit" disabled={isTesting || !selectedRetailer}>
                {isTesting ? 'Test loopt...' : 'Test kandidaat'}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setReceiptLineText('Taco saus')}>Voorbeeld Taco saus</Button>
              <Button type="button" variant="secondary" onClick={() => setReceiptLineText('Mexicaanse kruidenm.')}>Voorbeeld kruidenmix</Button>
              <Button type="button" variant="secondary" disabled={isSaving || !candidates.length} onClick={saveCandidateMatches}>{isSaving ? 'Opslaan...' : 'Kandidaten opslaan'}</Button>
            </div>
          </form>
          <div className="rz-external-databases-muted">Drempel probable_candidate: {formatScore(selectedRetailerConfig?.probable_candidate_threshold)}. Deze opslag maakt geen Mijn artikel, global_product of voorraadmutatie aan.</div>
          {saveResult ? <div className="rz-inline-feedback rz-inline-feedback--success">Kandidaten opgeslagen: {saveResult.saved_count ?? 0} nieuw, {saveResult.updated_count ?? 0} bijgewerkt, {saveResult.skipped_count ?? 0} overgeslagen.</div> : null}
          {matchResult ? (
            <Table dataTestId="external-database-candidates-table" tableClassName="rz-external-databases-table">
              <colgroup><col className="rz-external-databases-col-candidate" /><col className="rz-external-databases-col-brand" /><col className="rz-external-databases-col-code" /><col className="rz-external-databases-col-variant" /><col className="rz-external-databases-col-score" /><col className="rz-external-databases-col-status" /></colgroup>
              <thead><tr className="rz-table-header"><th>Kandidaat</th><th>Merk</th><th>Artikelnummer</th><th>Variant</th><th className="rz-num">Score</th><th>Status</th></tr></thead>
              <tbody>{candidates.length ? candidates.map((candidate) => <tr key={`${candidate.candidate_name}-${candidate.retailer_article_number}-${candidate.variant}`}><td>{candidate.candidate_name}</td><td>{candidate.candidate_brand}</td><td>{candidate.retailer_article_number}</td><td>{candidate.variant || '-'}</td><td className="rz-num">{formatScore(candidate.score)}</td><td><StatusBadge status={candidate.candidate_status} /></td></tr>) : <tr><td colSpan="6">Geen kandidaten gevonden boven de drempel.</td></tr>}</tbody>
            </Table>
          ) : null}
        </div>
      )
    }

    return (
      <Table dataTestId="external-database-retailers-table" tableClassName="rz-external-databases-retailer-table">
        <colgroup><col className="rz-external-databases-col-retailer" /><col className="rz-external-databases-col-retailer-status" /><col className="rz-external-databases-col-retailer-threshold" /><col className="rz-external-databases-col-retailer-examples" /></colgroup>
        <thead><tr className="rz-table-header"><th>Winkelketen</th><th>Status</th><th className="rz-num">Drempel</th><th>Voorbeelden</th></tr></thead>
        <tbody>{retailers.length ? retailers.map((retailer) => <tr key={retailer.retailer_code}><td>{retailer.retailer_name}</td><td>{retailer.status}</td><td className="rz-num">{formatScore(retailer.probable_candidate_threshold)}</td><td>{(retailer.supported_examples || []).join(', ')}</td></tr>) : <tr><td colSpan="4">Geen winkelketens gevonden.</td></tr>}</tbody>
      </Table>
    )
  }

  return (
    <AppShell title="Externe databases" showExit={false}>
      <div className="rz-external-databases" data-testid="external-databases-page">
        <ScreenCard fullWidth>
          <div className="rz-external-databases-card">
            <div className="rz-external-databases-header">
              <div className="rz-external-databases-title-group">
                <h2 className="rz-external-databases-title">Externe databases</h2>
                <p className="rz-external-databases-subtitle">Eerste versie voor externe productkandidaten. Deze preview maakt geen Mijn artikel, product of voorraadmutatie aan.</p>
              </div>
              <Button variant="primary" type="button" onClick={() => navigate('/home')}>Terug</Button>
            </div>
            <Tabs tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab}>{renderTabContent}</Tabs>
          </div>
        </ScreenCard>
      </div>
      <ErrorOverlay message={error} onClose={() => setError('')} />
    </AppShell>
  )
}

