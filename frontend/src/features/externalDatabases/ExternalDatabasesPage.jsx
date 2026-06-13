import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function StatusBadge({ status }) {
  const label = status || 'onbekend'
  return <span className="rz-inline-feedback" style={{ display: 'inline-flex', padding: '3px 8px' }}>{label}</span>
}

function OverviewTile({ title, value, helper }) {
  return (
    <div style={{ border: '1px solid #d5e5d8', borderRadius: 12, padding: 14, display: 'grid', gap: 6 }}>
      <strong>{title}</strong>
      <div style={{ fontSize: 28, color: '#2e7d4d', lineHeight: 1 }}>{value}</div>
      {helper ? <div style={{ color: '#5f7a68' }}>{helper}</div> : null}
    </div>
  )
}

export default function ExternalDatabasesPage() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('overzicht')
  const [summary, setSummary] = useState(null)
  const [retailers, setRetailers] = useState([])
  const [receiptLineText, setReceiptLineText] = useState('Mexicaanse kruidenm.')
  const [selectedRetailer, setSelectedRetailer] = useState('lidl')
  const [matchResult, setMatchResult] = useState(null)
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [isTesting, setIsTesting] = useState(false)
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

  const candidates = Array.isArray(matchResult?.candidates) ? matchResult.candidates : []
  const tabs = [
    ['overzicht', 'Overzicht'],
    ['test', 'Test algoritme'],
    ['winkelketens', 'Winkelketens'],
  ]

  return (
    <AppShell title="Externe databases" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="external-databases-page">
        <ScreenCard fullWidth>
          <div style={{ display: 'grid', gap: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
              <div style={{ display: 'grid', gap: 6 }}>
                <h2 style={{ margin: 0, color: '#2e7d4d' }}>Externe databases</h2>
                <p style={{ margin: 0, color: '#5f7a68' }}>
                  Eerste versie voor externe productkandidaten. Deze preview maakt geen Mijn artikel, product of voorraadmutatie aan.
                </p>
              </div>
              <Button variant="primary" type="button" onClick={() => navigate('/home')}>
                Terug
              </Button>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }} role="tablist" aria-label="Externe databases tabs">
              {tabs.map(([key, label]) => (
                <Button key={key} type="button" variant={activeTab === key ? 'primary' : 'secondary'} onClick={() => setActiveTab(key)}>
                  {label}
                </Button>
              ))}
            </div>

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

            {activeTab === 'overzicht' ? (
              <div style={{ display: 'grid', gap: 14 }}>
                {isLoadingConfig ? <div>Externe databases worden geladen...</div> : null}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                  <OverviewTile title="Actieve winkelketens" value={summary?.supported_retailers ?? retailers.length} helper={(summary?.active_retailers || []).join(', ') || 'Nog geen actieve winkelketens'} />
                  <OverviewTile title="Beleid" value="Preview" helper="Alleen kandidaatmatches tonen" />
                  <OverviewTile title="Productmutaties" value="0" helper="Niet toegestaan in v1" />
                </div>
                <p style={{ margin: 0, color: '#5f7a68' }}>
                  Deze module toont kandidaatmatches uit externe bronnen. Bevestigen, GTIN-invoer en OFF-verrijking volgen pas in latere opdrachten.
                </p>
              </div>
            ) : null}

            {activeTab === 'test' ? (
              <div style={{ display: 'grid', gap: 16 }}>
                <form onSubmit={testCandidateMatch} style={{ display: 'grid', gap: 12 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 260px) minmax(280px, 1fr)', gap: 12, alignItems: 'end' }}>
                    <label style={{ display: 'grid', gap: 4 }}>
                      <strong>Winkelketen</strong>
                      <select value={selectedRetailer} onChange={(event) => setSelectedRetailer(event.target.value)}>
                        {retailers.map((retailer) => (
                          <option key={retailer.retailer_code} value={retailer.retailer_code}>
                            {retailer.retailer_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ display: 'grid', gap: 4 }}>
                      <strong>Bonregel</strong>
                      <input value={receiptLineText} onChange={(event) => setReceiptLineText(event.target.value)} placeholder="Bijvoorbeeld: Mexicaanse kruidenm." />
                    </label>
                  </div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <Button type="submit" disabled={isTesting || !selectedRetailer}>
                      {isTesting ? 'Test loopt...' : 'Test kandidaat'}
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setReceiptLineText('Taco saus')}>
                      Voorbeeld Taco saus
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setReceiptLineText('Mexicaanse kruidenm.')}>
                      Voorbeeld kruidenmix
                    </Button>
                  </div>
                </form>

                <div style={{ color: '#5f7a68' }}>
                  Drempel probable_candidate: {formatScore(selectedRetailerConfig?.probable_candidate_threshold)}. Deze test schrijft geen data weg.
                </div>

                {matchResult ? (
                  <Table dataTestId="external-database-candidates-table" tableStyle={{ tableLayout: 'fixed', width: '100%', minWidth: 860 }}>
                    <colgroup>
                      <col style={{ width: '260px' }} />
                      <col style={{ width: '150px' }} />
                      <col style={{ width: '140px' }} />
                      <col style={{ width: '120px' }} />
                      <col style={{ width: '110px' }} />
                      <col style={{ width: '170px' }} />
                    </colgroup>
                    <thead>
                      <tr className="rz-table-header">
                        <th>Kandidaat</th>
                        <th>Merk</th>
                        <th>Artikelnummer</th>
                        <th>Variant</th>
                        <th className="rz-num">Score</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.length ? candidates.map((candidate) => (
                        <tr key={`${candidate.candidate_name}-${candidate.retailer_article_number}-${candidate.variant}`}>
                          <td>{candidate.candidate_name}</td>
                          <td>{candidate.candidate_brand}</td>
                          <td>{candidate.retailer_article_number}</td>
                          <td>{candidate.variant || '-'}</td>
                          <td className="rz-num">{formatScore(candidate.score)}</td>
                          <td><StatusBadge status={candidate.candidate_status} /></td>
                        </tr>
                      )) : (
                        <tr><td colSpan="6">Geen kandidaten gevonden boven de drempel.</td></tr>
                      )}
                    </tbody>
                  </Table>
                ) : null}
              </div>
            ) : null}

            {activeTab === 'winkelketens' ? (
              <Table dataTestId="external-database-retailers-table" tableStyle={{ tableLayout: 'fixed', width: '100%', minWidth: 720 }}>
                <colgroup>
                  <col style={{ width: '180px' }} />
                  <col style={{ width: '140px' }} />
                  <col style={{ width: '140px' }} />
                  <col style={{ width: '320px' }} />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th>Winkelketen</th>
                    <th>Status</th>
                    <th className="rz-num">Drempel</th>
                    <th>Voorbeelden</th>
                  </tr>
                </thead>
                <tbody>
                  {retailers.length ? retailers.map((retailer) => (
                    <tr key={retailer.retailer_code}>
                      <td>{retailer.retailer_name}</td>
                      <td>{retailer.status}</td>
                      <td className="rz-num">{formatScore(retailer.probable_candidate_threshold)}</td>
                      <td>{(retailer.supported_examples || []).join(', ')}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan="4">Geen winkelketens gevonden.</td></tr>
                  )}
                </tbody>
              </Table>
            ) : null}
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
