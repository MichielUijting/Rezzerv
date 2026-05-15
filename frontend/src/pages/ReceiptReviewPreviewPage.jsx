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
  parser_safety_notes: 'Veiligheidsnotities',
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

const COCKPIT_GROUPS = [
  {
    key: 'ready_for_review',
    title: 'Klaar voor controle',
    explanation: 'Deze bonnen lijken voldoende informatie te hebben om inhoudelijk te controleren.',
  },
  {
    key: 'rescan',
    title: 'Opnieuw scannen',
    explanation: 'De foto of scan lijkt onvoldoende; opnieuw fotograferen is waarschijnlijk sneller.',
  },
  {
    key: 'manual_entry',
    title: 'Handmatig invoeren',
    explanation: 'Er is te weinig bruikbare informatie om deze bon via OCR te beoordelen.',
  },
  {
    key: 'unclear',
    title: 'Technisch onduidelijk',
    explanation: 'Deze bonnen vragen eerst extra diagnose voordat ze nuttig beoordeeld kunnen worden.',
  },
]

function Badge({ children }) {
  return (
    <span style={{ display: 'inline-flex', border: '1px solid #d4ddd5', borderRadius: '999px', padding: '4px 10px', background: '#f6faf6', fontSize: '13px' }}>
      {children || '-'}
    </span>
  )
}

function userActionLabel(item = {}) {
  const readiness = item.readiness || ''
  const action = item.recommended_user_action || ''
  if (readiness === 'rescan_needed' || action === 'rescan') return 'Maak een betere foto of scan'
  if (readiness === 'manual_entry_needed' || action === 'manual_entry') return 'Voer deze bon handmatig in'
  if (readiness === 'insufficient_diagnostics') return 'Laat deze bon technisch onderzoeken'
  return 'Controleer winkelnaam, totaalbedrag en artikelregels'
}

function reasonLabel(item = {}) {
  const mainReason = String(item.main_reason || '').toLowerCase()
  const readiness = item.readiness || ''
  if (readiness === 'rescan_needed') return 'De beeldkwaliteit lijkt onvoldoende.'
  if (readiness === 'manual_entry_needed') return 'Er is te weinig betrouwbare OCR-informatie.'
  if (readiness === 'insufficient_diagnostics') return 'De diagnose is nog niet bruikbaar genoeg.'
  if (mainReason.includes('ocr')) return 'De OCR-regels zijn nog onzeker.'
  if (mainReason.includes('image')) return 'De foto of scan vraagt aandacht.'
  if (Number(item.ocr_issue_count || 0) > 0) return 'Er zijn OCR-signalen die gecontroleerd moeten worden.'
  return 'De bon vraagt menselijke controle voordat verwerking veilig is.'
}

function cockpitGroupKey(item = {}) {
  const readiness = item.readiness || ''
  const action = item.recommended_user_action || ''
  if (readiness === 'rescan_needed' || action === 'rescan') return 'rescan'
  if (readiness === 'manual_entry_needed' || action === 'manual_entry') return 'manual_entry'
  if (readiness === 'insufficient_diagnostics') return 'unclear'
  return 'ready_for_review'
}

function DiagnosticItem({ item }) {
  const title = item?.title || item?.code || 'Signaal'
  const description = item?.description || item?.finding || ''
  return (
    <li style={{ border: '1px solid #e1e6e1', borderRadius: '12px', padding: '12px', background: '#fff' }}>
      <div style={{ fontWeight: 600 }}>{title}</div>
      {description ? <div style={{ marginTop: '4px' }}>{description}</div> : null}
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
    ['OCR-signalen', normalized.ocr_issues?.length || 0],
    ['Beeldsignalen', normalized.image_issues?.length || 0],
    ['Aanbevelingen', normalized.preprocessing_recommendations?.length || 0],
    ['Reviewtaken', normalized.review_tasks?.length || 0],
  ]

  return (
    <Card>
      <div style={{ display: 'grid', gap: '12px' }}>
        <h2 style={{ margin: 0 }}>{data.receipt_id || 'Kassabon'}</h2>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <Badge>Bron: {data.source_file || '-'}</Badge>
          <Badge>Advies: {userActionLabel({ recommended_user_action: explainability.recommended_user_action })}</Badge>
          <Badge>Reden: {reasonLabel({ main_reason: explainability.main_reason })}</Badge>
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
          <strong>Wat moet ik doen?</strong>
          {(explainability.review_rationale || []).length ? (
            <ul style={{ marginBottom: 0 }}>
              {(explainability.review_rationale || []).map((line, index) => <li key={index}>{line}</li>)}
            </ul>
          ) : (
            <div style={{ marginTop: '8px', color: '#5f6f64' }}>Controleer deze bon handmatig voordat verwerking wordt overwogen.</div>
          )}
        </div>
      </div>
    </Card>
  )
}

function ReceiptCard({ item, isSelected, onSelect }) {
  return (
    <div style={{ border: isSelected ? '2px solid #0f3d24' : '1px solid #d9e1da', borderRadius: '14px', padding: '12px', background: '#fff', display: 'grid', gap: '8px' }}>
      <div style={{ fontWeight: 700 }}>{item.receipt_id || item.file_name}</div>
      <div><strong>Advies:</strong> {userActionLabel(item)}</div>
      <div><strong>Reden:</strong> {reasonLabel(item)}</div>
      <div><strong>Te doen:</strong> {userActionLabel(item)}</div>
      <div style={{ color: '#5f6f64', fontSize: '13px' }}>
        OCR-signalen: {item.ocr_issue_count || 0} · Reviewtaken: {item.review_task_count || 0}
      </div>
      <button
        type="button"
        onClick={() => onSelect(item.json_path)}
        style={{
          border: '1px solid #d4ddd5',
          borderRadius: '10px',
          padding: '8px 12px',
          background: '#0f3d24',
          color: '#fff',
          cursor: 'pointer',
          justifySelf: 'start',
        }}
      >
        Details bekijken
      </button>
    </div>
  )
}

function AdminCockpit({ items, selectedPath, onSelect }) {
  const grouped = COCKPIT_GROUPS.reduce((acc, group) => ({ ...acc, [group.key]: [] }), {})
  items.forEach((item) => {
    const key = cockpitGroupKey(item)
    grouped[key] = grouped[key] || []
    grouped[key].push(item)
  })

  return (
    <Card>
      <div style={{ display: 'grid', gap: '18px' }}>
        <div>
          <h2 style={{ margin: 0 }}>Kassaboncontrole</h2>
          <div style={{ color: '#5f6f64' }}>Read-only overzicht: welke bonnen vragen aandacht en wat is de menselijke vervolgstap?</div>
        </div>

        {COCKPIT_GROUPS.map((group) => {
          const groupItems = grouped[group.key] || []
          return (
            <section key={group.key} style={{ display: 'grid', gap: '10px' }}>
              <h3 style={{ margin: 0 }}>{group.title} ({groupItems.length})</h3>
              <div style={{ color: '#5f6f64' }}>{group.explanation}</div>
              {groupItems.length ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
                  {groupItems.map((item) => (
                    <ReceiptCard key={item.json_path} item={item} isSelected={item.json_path === selectedPath} onSelect={onSelect} />
                  ))}
                </div>
              ) : (
                <div style={{ border: '1px dashed #ccd8cf', borderRadius: '12px', padding: '12px', color: '#5f6f64', background: '#fbfdfb' }}>
                  Geen bonnen in deze groep.
                </div>
              )}
            </section>
          )
        })}
      </div>
    </Card>
  )
}

export default function ReceiptReviewPreviewPage() {
  const [jsonPath, setJsonPath] = useState(DEFAULT_JSON_PATH)
  const [readinessItems, setReadinessItems] = useState([])
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [error, setError] = useState('')
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false)

  const normalized = useMemo(() => data?.normalized_review_diagnostics || {}, [data])

  useEffect(() => {
    async function loadInitialData() {
      setIsLoadingList(true)
      try {
        const readinessResponse = await fetchJson('/api/receipt-ingestion/review-readiness-baseline')
        setReadinessItems(Array.isArray(readinessResponse?.items) ? readinessResponse.items : [])
      } catch {
        setReadinessItems([])
      } finally {
        setIsLoadingList(false)
      }
    }

    loadInitialData()
  }, [])

  async function loadPreview(pathOverride) {
    const pathValue = String(pathOverride || jsonPath || '').trim()
    if (!pathValue) {
      setError('Vul eerst een JSON-pad in.')
      return
    }

    setJsonPath(pathValue)
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
    <AppShell title="Kassaboncontrole" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-review-preview-page">
        <Card>
          <div style={{ display: 'grid', gap: '12px' }}>
            <div>
              <strong>Doel</strong>
              <div>Bekijk welke kassabonnen aandacht nodig hebben. Dit scherm is alleen-lezen: er wordt niets opgeslagen of verwerkt.</div>
            </div>

            {isLoadingList ? <span>Bonnen laden...</span> : null}
            {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          </div>
        </Card>

        {readinessItems.length ? (
          <AdminCockpit items={readinessItems} selectedPath={jsonPath} onSelect={loadPreview} />
        ) : (
          <Card>
            <div style={{ color: '#5f6f64' }}>Geen actieve testbonnen beschikbaar.</div>
          </Card>
        )}

        {data ? (
          <>
            <SummaryCard data={data} />

            <Card>
              <div style={{ display: 'grid', gap: '12px' }}>
                <Button variant="secondary" onClick={() => setShowTechnicalDetails((current) => !current)}>
                  {showTechnicalDetails ? 'Technische details verbergen' : 'Technische details tonen'}
                </Button>
                {showTechnicalDetails ? (
                  <div style={{ display: 'grid', gap: '18px' }}>
                    <label htmlFor="receipt-review-json-path"><strong>Technisch JSON-pad</strong></label>
                    <Input
                      id="receipt-review-json-path"
                      value={jsonPath}
                      onChange={(event) => setJsonPath(event.target.value)}
                      placeholder="tools/receipt_csv_poc/test_runs/.../json/bestand.json"
                    />
                    <Button onClick={() => loadPreview()} disabled={isLoading}>{isLoading ? 'Laden...' : 'Preview opnieuw laden'}</Button>
                    {GROUP_ORDER.map((groupName) => (
                      <DiagnosticGroup key={groupName} name={groupName} items={normalized[groupName]} />
                    ))}
                  </div>
                ) : null}
              </div>
            </Card>
          </>
        ) : null}
      </div>
    </AppShell>
  )
}
