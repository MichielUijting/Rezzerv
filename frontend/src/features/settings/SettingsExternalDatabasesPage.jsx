import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { getExternalDatabasesConfig, previewRetailerExternalDatabaseMatch } from './services/externalDatabasesService'

function formatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

export default function SettingsExternalDatabasesPage() {
  const [config, setConfig] = useState(null)
  const [retailerCode, setRetailerCode] = useState('lidl')
  const [receiptLineText, setReceiptLineText] = useState('Mexicaanse kruidenm.')
  const [preview, setPreview] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [error, setError] = useState('')
  const [previewError, setPreviewError] = useState('')

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      setError('')
      try {
        const data = await getExternalDatabasesConfig()
        if (!active) return
        setConfig(data)
        setRetailerCode(data?.supported_retailer_codes?.[0] || 'lidl')
      } catch (loadError) {
        if (!active) return
        setError(loadError?.message || 'Configuratie kon niet worden geladen.')
      } finally {
        if (active) setIsLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [])

  const selectedRetailer = useMemo(() => {
    return (config?.retailers || []).find((retailer) => retailer.retailer_code === retailerCode) || null
  }, [config, retailerCode])

  async function handlePreview() {
    setPreviewError('')
    setIsPreviewing(true)
    try {
      setPreview(await previewRetailerExternalDatabaseMatch(retailerCode, receiptLineText, true))
    } catch (matchError) {
      setPreviewError(matchError?.message || 'Match-preview kon niet worden uitgevoerd.')
    } finally {
      setIsPreviewing(false)
    }
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '20px' }} data-testid="external-databases-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Externe databases</h2>
            <p style={{ margin: 0, color: '#667085' }}>Configureer per winkelketen hoe Rezzerv externe productkandidaten bepaalt.</p>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Link to="/instellingen" style={{ color: '#0f5b32', textDecoration: 'none', fontWeight: 600 }}>← Terug naar instellingen</Link>
          </div>
          {isLoading ? <div>Configuratie laden…</div> : null}
          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          {!isLoading && !error && selectedRetailer ? (
            <>
              <div className="rz-automation-setting-card" style={{ alignItems: 'stretch' }}>
                <div className="rz-automation-setting-copy">
                  <div className="rz-automation-setting-title">Algoritme per winkelketen</div>
                  <div className="rz-automation-setting-text">Huidige winkelketen: <strong>{selectedRetailer.retailer_name}</strong>. Drempel: <strong>{formatScore(selectedRetailer.probable_candidate_threshold)}</strong>.</div>
                </div>
                <div style={{ minWidth: '240px', display: 'grid', gap: '10px' }}>
                  <select value={retailerCode} onChange={(event) => setRetailerCode(event.target.value)}>
                    {(config?.retailers || []).map((retailer) => <option key={retailer.retailer_code} value={retailer.retailer_code}>{retailer.retailer_name}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ fontWeight: 600 }}>Scoreweging</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                  {Object.entries(selectedRetailer.score_weights || {}).map(([key, value]) => (
                    <div key={key} style={{ padding: '12px 14px', border: '1px solid #dfe4ea', borderRadius: '12px' }}>
                      <div style={{ fontWeight: 600 }}>{key}</div>
                      <div style={{ color: '#667085' }}>{formatScore(value)}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ fontWeight: 600 }}>Termbibliotheek</div>
                <div style={{ overflowX: 'auto' }}>
                  <table className="rz-table" style={{ minWidth: '640px' }}>
                    <thead><tr><th>Term</th><th>Expansies</th></tr></thead>
                    <tbody>
                      {(selectedRetailer.term_library || []).map((rule) => <tr key={rule.term}><td>{rule.term}</td><td>{(rule.expansions || []).join(', ')}</td></tr>)}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ fontWeight: 600 }}>Test bonregel</div>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <input value={receiptLineText} onChange={(event) => setReceiptLineText(event.target.value)} style={{ flex: '1 1 260px' }} />
                  <Button onClick={handlePreview} disabled={isPreviewing || !receiptLineText.trim()}>{isPreviewing ? 'Testen…' : 'Test kandidaat'}</Button>
                </div>
                {previewError ? <div className="rz-inline-feedback rz-inline-feedback--error">{previewError}</div> : null}
              </div>

              {preview ? (
                <div style={{ display: 'grid', gap: '10px' }}>
                  <div style={{ fontWeight: 600 }}>Preview kandidaten</div>
                  <div style={{ color: '#667085', fontSize: '14px' }}>Genormaliseerde termen: {(preview.normalized_terms || []).join(', ') || '—'}</div>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="rz-table" style={{ minWidth: '900px' }}>
                      <thead><tr><th>Kandidaat</th><th>Merk</th><th>Artikelnummer</th><th>Variant</th><th>Score</th><th>Status</th></tr></thead>
                      <tbody>
                        {(preview.candidates || []).map((candidate) => (
                          <tr key={`${candidate.candidate_name}-${candidate.retailer_article_number || ''}`}>
                            <td>{candidate.candidate_name}</td>
                            <td>{candidate.candidate_brand || '—'}</td>
                            <td>{candidate.retailer_article_number || '—'}</td>
                            <td>{candidate.variant || '—'}</td>
                            <td>{formatScore(candidate.score)}</td>
                            <td>{candidate.candidate_status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </Card>
    </AppShell>
  )
}
