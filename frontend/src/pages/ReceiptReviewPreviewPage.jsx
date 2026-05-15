import { useMemo, useState } from 'react'
import AppShell from '../app/AppShell.jsx'
import Card from '../ui/Card.jsx'
import Button from '../ui/Button.jsx'
import Input from '../ui/Input.jsx'
import { fetchJson, normalizeErrorMessage } from '../features/stores/storeImportShared.jsx'

const DEFAULT_JSON_PATH = 'tools/receipt_csv_poc/test_runs/run_20260514_140310_preprocessing_diag/json/AH foto 2.json'

const GROUP_LABELS = {
  ocr_issues: 'OCR-problemen',
  image_issues: 'Beeldproblemen',
  preprocessing_recommendations: 'Preprocessing-aanbevelingen',
  consensus_groups: 'Consensusgroepen',
  parser_safety_notes: 'Parser-safety notities',
  review_tasks: 'Reviewtaken',
}

const GROUP_ORDER = [
  'ocr_issues',
  'image_issues',
  'preprocessing_recommendations',
  'consensus_groups',
  'parser_safety_notes',
  'review_tasks',
]

function Badge({ children }) {
  return (
    <span style={{ display: 'inline-flex', border: '1px solid #d4ddd5', borderRadius: '999px', padding: '4px 10px', background: '#f6faf6', fontSize: '13px' }}>
      {children || '-'}
    </span>
  )
}

function DiagnosticItem({ item }) {
  const title = item?.title || item?.code || 'Signaal'
  const description = item?.description || item?.finding || ''
  const meta = [item?.severity, item?.priority, item?.source].filter(Boolean).join(' · ')
  return (
    <li style={{ border: '1px solid #e1e6e1', borderRadius: '12px', padding: '12px', background: '#fff' }}>
      <div style={{ fontWeight: 600 }}>{title}</div>
      {description ? <div style={{ marginTop: '4px' }}>{description}</div> : null}
      {meta ? <div style={{ marginTop: '6px', color: '#5f6f64', fontSize: '13px' }}>{meta}</div> : null}
    </li>
  )
}

function DiagnosticGroup({ name, items }) {
  const safeItems = Array.isArray(items) ? items : []
  return (
    <section style={{ display: 'grid', gap: '10px' }}>
      <h3 style={{ margin: 0 }}>{GROUP_LABELS[name] || name}</h3>
      {safeItems.length ? (
        <ul style={{ display: 'grid', gap: '8px', listStyle: 'none', padding: 0, margin: 0 }}>
          {safeItems.map((item, index) => <DiagnosticItem key={`${name}-${index}`} item={item} />)}
        </ul>
      ) : (
        <div style={{ border: '1px dashed #ccd8cf', borderRadius: '12px', padding: '12px', color: '#5f6f64', background: '#fbfdfb' }}>
          Geen signalen beschikbaar.
        </div>
      )}
    </section>
  )
}

export default function ReceiptReviewPreviewPage() {
  const [jsonPath, setJsonPath] = useState(DEFAULT_JSON_PATH)
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const normalized = useMemo(() => data?.normalized_review_diagnostics || {}, [data])
  const explainability = data?.explainability || {}
  const recommendedAction = explainability?.recommended_user_action || data?.diagnostics?.diagnostics_summary?.recommended_user_action || '-'

  async function loadPreview() {
    const pathValue = String(jsonPath || '').trim()
    if (!pathValue) {
      setError('Vul eerst een JSON-pad in.')
      return
    }
    setIsLoading(true)
    setError('')
    try {
      const response = await fetchJson(`/api/receipt-ingestion/explainability-preview?json_path=${encodeURIComponent(pathValue)}`)
      setData(response)
    } catch (err) {
      setData(null)
      setError(normalizeErrorMessage(err?.message) || 'Review-preview kon niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AppShell title="Receipt Review Preview" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-review-preview-page">
        <Card>
          <div style={{ display: 'grid', gap: '12px' }}>
            <div>
              <strong>Doel</strong>
              <div>Read-only preview van explainability en genormaliseerde reviewdiagnostics. Dit scherm schrijft niets weg en verwerkt geen kassabon.</div>
            </div>
            <label htmlFor="receipt-review-json-path"><strong>POC JSON-pad</strong></label>
            <Input
              id="receipt-review-json-path"
              value={jsonPath}
              onChange={(event) => setJsonPath(event.target.value)}
              placeholder="tools/receipt_csv_poc/test_runs/.../json/bestand.json"
            />
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <Button onClick={loadPreview} disabled={isLoading}>{isLoading ? 'Laden...' : 'Preview laden'}</Button>
            </div>
            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          </div>
        </Card>

        {data ? (
          <>
            <Card>
              <div style={{ display: 'grid', gap: '12px' }}>
                <h2 style={{ margin: 0 }}>{data.receipt_id || 'Kassabon'}</h2>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <Badge>Bron: {data.source_file || '-'}</Badge>
                  <Badge>Engine: {data.engine_processing_state || '-'}</Badge>
                  <Badge>Advies: {recommendedAction}</Badge>
                  <Badge>Hoofdreden: {explainability.main_reason || '-'}</Badge>
                </div>
                <div style={{ border: '1px solid #e1e6e1', borderRadius: '12px', padding: '12px', background: '#fbfdfb' }}>
                  <strong>Waarom review?</strong>
                  <ul style={{ marginBottom: 0 }}>
                    {(explainability.review_rationale || []).map((line, index) => <li key={index}>{line}</li>)}
                  </ul>
                </div>
              </div>
            </Card>

            <Card>
              <div style={{ display: 'grid', gap: '18px' }}>
                {GROUP_ORDER.map((groupName) => (
                  <DiagnosticGroup key={groupName} name={groupName} items={normalized[groupName]} />
                ))}
              </div>
            </Card>
          </>
        ) : null}
      </div>
    </AppShell>
  )
}
