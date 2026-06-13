import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function StatusBadge({ status }) {
  const label = status || 'onbekend'
  return (
    <span style={{ border: '1px solid #2e7d4d', borderRadius: 999, padding: '3px 8px', color: '#2e7d4d', fontSize: 12 }}>
      {label}
    </span>
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
          setRetailers(Array.isArray(retailersData?.retailers) ? retailersData.retailers : [])
          const firstRetailerCode = retailersData?.retailers?.[0]?.retailer_code
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

  return (
    <div className="rz-screen">
      <Header title="Externe databases" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div style={{ display: 'grid', gap: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
                <div style={{ display: 'grid', gap: 6 }}>
                  <h2 style={{ margin: 0, color: '#2e7d4d' }}>Externe databases</h2>
                  <p style={{ margin: 0, color: '#5f7a68' }}>
                    Eerste versie voor externe productkandidaten. Deze preview maakt geen Mijn artikel, product of voorraadmutatie aan.
                  </p>
                </div>
                <Button variant="secondary" type="button" onClick={() => navigate('/home')}>
                  Terug
                </Button>
              </div>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }} role="tablist" aria-label="Externe databases tabs">
                {[
                  ['overzicht', 'Overzicht'],
                  ['test', 'Test algoritme'],
                  ['winkelketens', 'Winkelketens'],
                ].map(([key, label]) => (
                  <Button key={key} type="button" variant={activeTab === key ? 'primary' : 'secondary'} onClick={() => setActiveTab(key)}>
                    {label}
                  </Button>
                ))}
              </div>

              {error ? (
                <div style={{ border: '1px solid #b3261e', borderRadius: 12, padding: 12, color: '#b3261e', background: '#fff7f6' }}>
                  {error}
                </div>
              ) : null}

              {activeTab === 'overzicht' ? (
                <div style={{ display: 'grid', gap: 14 }}>
                  {isLoadingConfig ? <div>Externe databases worden geladen...</div> : null}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                    <div style={{ border: '1px solid #d5e5d8', borderRadius: 12, padding: 14 }}>
                      <strong>Actieve winkelketens</strong>
                      <div style={{ fontSize: 28, color: '#2e7d4d' }}>{summary?.supported_retailers ?? retailers.length}</div>
                    </div>
                    <div style={{ border: '1px solid #d5e5d8', borderRadius: 12, padding: 14 }}>
                      <strong>Beleid</strong>
                      <div style={{ color: '#5f7a68', marginTop: 6 }}>Preview only</div>
                    </div>
                    <div style={{ border: '1px solid #d5e5d8', borderRadius: 12, padding: 14 }}>
                      <strong>Productmutaties</strong>
                      <div style={{ color: '#5f7a68', marginTop: 6 }}>Niet toegestaan in v1</div>
                    </div>
                  </div>
                  <p style={{ margin: 0, color: '#5f7a68' }}>
                    Deze module toont kandidaatmatches uit externe bronnen. Bevestigen, GTIN-invoer en OFF-verrijking volgen pas in latere opdrachten.
                  </p>
                </div>
              ) : null}

              {activeTab === 'test' ? (
                <div style={{ display: 'grid', gap: 16 }}>
                  <form onSubmit={testCandidateMatch} style={{ display: 'grid', gap: 12 }}>
                    <label style={{ display: 'grid', gap: 4 }}>
                      <span>Winkelketen</span>
                      <select value={selectedRetailer} onChange={(event) => setSelectedRetailer(event.target.value)}>
                        {retailers.map((retailer) => (
                          <option key={retailer.retailer_code} value={retailer.retailer_code}>
                            {retailer.retailer_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ display: 'grid', gap: 4 }}>
                      <span>Bonregel</span>
                      <input value={receiptLineText} onChange={(event) => setReceiptLineText(event.target.value)} placeholder="Bijvoorbeeld: Mexicaanse kruidenm." />
                    </label>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
                    <div style={{ overflowX: 'auto' }}>
                      <table className="rz-table" style={{ width: '100%', minWidth: 760 }}>
                        <thead>
                          <tr>
                            <th>Kandidaat</th>
                            <th>Merk</th>
                            <th>Artikelnummer</th>
                            <th>Variant</th>
                            <th>Score</th>
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
                              <td>{formatScore(candidate.score)}</td>
                              <td><StatusBadge status={candidate.candidate_status} /></td>
                            </tr>
                          )) : (
                            <tr><td colSpan="6">Geen kandidaten gevonden boven de drempel.</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {activeTab === 'winkelketens' ? (
                <div style={{ display: 'grid', gap: 12 }}>
                  {retailers.map((retailer) => (
                    <div key={retailer.retailer_code} style={{ border: '1px solid #d5e5d8', borderRadius: 12, padding: 14, display: 'grid', gap: 6 }}>
                      <strong>{retailer.retailer_name}</strong>
                      <div>Status: {retailer.status}</div>
                      <div>Drempel: {formatScore(retailer.probable_candidate_threshold)}</div>
                      <div>Voorbeelden: {(retailer.supported_examples || []).join(', ')}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
