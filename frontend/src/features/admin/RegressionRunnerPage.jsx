import React from 'react'
import { getRezzervVersionTag } from '../../ui/version'
import { runLayer1Tests, runLayer2Tests, runLayer3Tests, submitTestResults } from './services/adminTestingService'
import { runLayer1RegressionTests } from './lib/layer1RegressionRunner'
import { runLayer2RouteTests } from './lib/layer2RouteRunner'
import { runLayer3StyleguideTests } from './lib/layer3StyleguideRunner'

const FIXTURE_KEY = 'rezzerv_layer1_fixture'
const PROGRESS_KEY = 'rezzerv_regression_progress'

function nowIso() { return new Date().toISOString() }

function clearRunnerLocalState() {
  try {
    window.localStorage.removeItem(FIXTURE_KEY)
    window.localStorage.removeItem(PROGRESS_KEY)
  } catch {}
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) throw new Error(data?.detail || data?.message || `${path} gaf status ${response.status}`)
  return data
}

async function resetRegressionDataset() {
  clearRunnerLocalState()
  const resetInfo = await requestJson('/api/dev/regression/reset', { method: 'POST', body: '{}' })
  const fixture = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
  try {
    window.localStorage.setItem(FIXTURE_KEY, JSON.stringify({
      articleId: null,
      batchId: fixture?.batchId || fixture?.batch_id || null,
      completeLineId: fixture?.completeLineId || fixture?.complete_line_id || null,
      incompleteLineId: fixture?.incompleteLineId || fixture?.incomplete_line_id || null,
      batchMatchText: 'Jumbo',
      completeLineLabel: 'Magere yoghurt',
      incompleteLineLabel: 'Appelsap',
      connectionId: fixture?.connectionId || fixture?.connection_id || null,
      latestBatchId: fixture?.latestBatchId || fixture?.latest_batch_id || fixture?.batchId || fixture?.batch_id || null,
    }))
  } catch {}
  return { resetInfo, fixture }
}

async function runLayerSuite(layerId, startFn, runnerFn) {
  const reset = await resetRegressionDataset()
  const startedAt = nowIso()
  const start = await startFn()
  if (start?.started === false) throw new Error(`Kon ${layerId} niet starten omdat er al een test loopt`)
  const results = await runnerFn()
  await submitTestResults(layerId, results)
  const passed = results.filter((item) => item.status === 'passed').length
  const failed = results.filter((item) => item.status === 'failed').length
  return { id: layerId, status: failed > 0 ? 'failed' : 'passed', started_at: startedAt, finished_at: nowIso(), passed_count: passed, failed_count: failed, reset, results }
}

function toSummary(report) {
  const lines = []
  lines.push(`Versie: ${report.version}`)
  lines.push(`Status: ${report.overall_status}`)
  lines.push(`Start: ${report.started_at}`)
  lines.push(`Einde: ${report.finished_at}`)
  lines.push('')
  for (const layer of report.layers || []) {
    lines.push(`${layer.id}: ${layer.status} (${layer.passed_count} geslaagd / ${layer.failed_count} gefaald)`)
    for (const result of layer.results || []) lines.push(`- ${result.status === 'passed' ? 'OK' : 'FAIL'} ${result.name}${result.error ? ` — ${result.error}` : ''}`)
    lines.push('')
  }
  if (report.fatal_error) lines.push(`Fatale regressiefout: ${report.fatal_error}`)
  return lines.join('\n').trim()
}

export default function RegressionRunnerPage() {
  const [status, setStatus] = React.useState('idle')
  const [report, setReport] = React.useState(null)
  const [error, setError] = React.useState('')
  const hasStartedRef = React.useRef(false)

  React.useEffect(() => {
    if (hasStartedRef.current) return undefined
    hasStartedRef.current = true
    let cancelled = false
    async function run() {
      setStatus('running')
      setError('')
      const startedAt = nowIso()
      try {
        const layers = []
        layers.push(await runLayerSuite('layer1', runLayer1Tests, runLayer1RegressionTests))
        layers.push(await runLayerSuite('layer2', runLayer2Tests, runLayer2RouteTests))
        layers.push(await runLayerSuite('layer3', runLayer3Tests, runLayer3StyleguideTests))
        const overallStatus = layers.some((layer) => layer.status !== 'passed') ? 'failed' : 'passed'
        const nextReport = { version: getRezzervVersionTag(), started_at: startedAt, finished_at: nowIso(), overall_status: overallStatus, layers, summary_text: '' }
        nextReport.summary_text = toSummary(nextReport)
        if (!cancelled) { setReport(nextReport); setStatus('completed'); window.__REZZERV_REGRESSION_RESULT__ = nextReport }
      } catch (runError) {
        const failedReport = { version: getRezzervVersionTag(), started_at: startedAt, finished_at: nowIso(), overall_status: 'failed', layers: [], summary_text: '', fatal_error: runError?.message || 'Onbekende regressiefout' }
        failedReport.summary_text = toSummary(failedReport)
        if (!cancelled) { setReport(failedReport); setError(failedReport.fatal_error); setStatus('completed'); window.__REZZERV_REGRESSION_RESULT__ = failedReport }
      }
    }
    run()
    return () => { cancelled = true }
  }, [])

  return (
    <main data-testid="regression-runner-page" style={{ padding: 24, fontFamily: 'Arial, sans-serif' }}>
      <h1>Rezzerv regressierunner</h1>
      <p data-testid="regression-runner-version">Rezzerv v{getRezzervVersionTag()}</p>
      <p data-testid="regression-runner-status" data-status={status}>{status}</p>
      {error ? <p data-testid="regression-runner-error">{error}</p> : null}
      <pre data-testid="regression-runner-json" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{report ? JSON.stringify(report, null, 2) : ''}</pre>
      <pre data-testid="regression-runner-summary" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{report?.summary_text || ''}</pre>
    </main>
  )
}
