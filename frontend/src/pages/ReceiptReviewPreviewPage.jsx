import { useEffect, useMemo, useState } from 'react'
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

function SummaryCard({ data }) {
  const normalized = data?.normalized_review_diagnostics || {}
  const explainability = data?.explainability || {}

  const summaryItems = [
    ['OCR-issues', normalized.ocr_issues?.length || 0],
    ['Beeldproblemen', normalized.image_issues?.length || 0],
    ['Preprocessing', normalized.preprocessing_recommendations?.length || 0],
    ['Parser-safety', normalized.parser_safety_notes?.length || 0],
    ['Reviewtaken', normalized.review_tasks?.length || 0],
  ]

  return (
    <Card>
      <div style={{ display: 'grid', gap: '12px' }}>
        <h2 style={{ margin: 0 }}>{data.receipt_id || 'Kassabon'}</h2>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <Badge>Bron: {data.source_file || '-'}</Badge>
          <Badge>Engine: {data.engine_processing_state || '-'}</Badge>
          <Badge>Advies: {explainability.recommended_user_action || '-'}</Badge>
          <Badge>Hoofdreden: {explainability.main_reason || '-'}</Badge>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px' }}>
          {summaryItems.map(([label, count]) => (
            <div key={label} style={{ border: '1px solid #d9e1da', borderRadius: '12px', padding: '12px', background: '#fbfdfb' }}>
              <div style={{ color: '#5f6f64', fontSize: '13px' }}>{label}</div>
              <div style={{ fontWeight: 700, fontSize: '24px' }}>{count}</div>
            </div>
          ))}
        </div>

        <div style={{ border: '1px solid #e1e6e1', borderRadius: '12px', padding: '12px', background: '#fbfdfb' }}>
          <strong>Waarom review?</strong>
          {(explainability.review_rationale || []).length ? (
            <ul style={{ marginBottom: 0 }}>
              {(explainability.review_rationale || []).map((line, index) => <li key={index}>{line}</li>)}
            </ul>
          ) : (
            <div style={{ marginTop: '8px', color: '#5f6f64' }}>Geen review-rationale beschikbaar.</div>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function ReceiptReviewPreviewPage() {
  const [jsonPath, setJsonPath] = useState(DEFAULT_JSON_PATH)
  const [availableJsons, setAvailableJsons] = useState([])
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [error, setError] = useState('')

  const normalized = useMemo(() => data?.normalized_review_diagnostics || {}, [data])

  useEffect(() => {
    async function loadJsonList() {
      setIsLoadingList(true)
      try {
        const response = await fetchJson('/api/receipt-ingestion/test-run-jsons')
        setAvailableJsons(Array.isArray(response?.items) ? response.items : [])
      } catch {
        setAvailableJsons([])
      } finally {
        setIsLoadingList(false)
      }
    }

    loadJsonList()
  }, [])

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

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <Button onClick={loadPreview} disabled={isLoading}>{isLoading ? 'Laden...' : 'Preview laden'}</Button>
              {isLoadingList ? <span>Testset laden...</span> : null}
            </div>

            {availableJsons.length ? (
              <div style={{ display: 'grid', gap: '8px' }}>
                <strong>Beschikbare testbonnen</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {availableJsons.slice(0, 24).map((item) => (
                    <button
                      key={item.json_path}
                      type="button"
                      onClick={() => setJsonPath(item.json_path)}
                      style={{
                        border: '1px solid #d4ddd5',
                        borderRadius: '999px',
                        padding: '6px 10px',
                        background: item.json_path === jsonPath ? '#0f3d24' : '#fff',
                        color: item.json_path === jsonPath ? '#fff' : '#1e2a22',
                        cursor: 'pointer',
                      }}
                    >
                      {item.file_name}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ border: '1px dashed #ccd8cf', borderRadius: '12px', padding: '12px', color: '#5f6f64', background: '#fbfdfb' }}>
                Geen testbonnenlijst beschikbaar. Handmatige invoer blijft mogelijk.
              </div>
            )}

            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          </div>
        </Card>

        {data ? (
          <>
            <SummaryCard data={data} />

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
