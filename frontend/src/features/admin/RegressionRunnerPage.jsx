import React from 'react'
import { getRezzervVersionTag } from '../../ui/version'
import { runLayer1Tests, runLayer2Tests, runLayer3Tests, submitTestResults } from './services/adminTestingService'
import { runLayer1RegressionTests } from './lib/layer1RegressionRunner'
import { runLayer2RouteTests } from './lib/layer2RouteRunner'
import { runLayer3StyleguideTests } from './lib/layer3StyleguideRunner'

import { resetRegressionDataset } from './lib/regressionFixtureSetup'

const LAYER_TIMEOUT_MS = 120000
const RUNNER_TIMEOUT_MS = 240000

function nowIso() { return new Date().toISOString() }

function timeoutPromise(ms, label) {
  return new Promise((_, reject) => {
    window.setTimeout(() => reject(new Error(`${label} timeout na ${ms} ms`)), ms)
  })
}

async function withTimeout(factory, ms, label) {
  return Promise.race([factory(), timeoutPromise(ms, label)])
}

function normalizeLayerError(error, fallback) {
  return error?.message || fallback || 'Onbekende fout'
}

async function runApiAlmostOutSelfTestLayer() {
  const startedAt = nowIso()
  const response = await fetch('/api/dev/regression/almost-out-self-test', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: '{}',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || payload?.message || `Almost-out backend self-test gaf status ${response.status}`)
  const results = Array.isArray(payload?.results) ? payload.results : []
  const passed = results.filter((item) => item.status === 'passed').length
  const failed = results.filter((item) => item.status === 'failed').length
  return {
    id: 'api-almost-out-self-test',
    status: failed > 0 || String(payload?.status || '').toLowerCase() === 'failed' ? 'failed' : 'passed',
    started_at: startedAt,
    finished_at: nowIso(),
    passed_count: passed,
    failed_count: failed,
    results,
  }
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

function createFailedLayer(id, startedAt, error, reset = null) {
  const message = normalizeLayerError(error, `${id} faalde`)
  return {
    id,
    status: 'failed',
    started_at: startedAt,
    finished_at: nowIso(),
    passed_count: 0,
    failed_count: 1,
    reset,
    results: [{ name: id, status: 'failed', error: message }],
  }
}

async function runLayerSafely(id, runner, timeoutMs = LAYER_TIMEOUT_MS) {
  const startedAt = nowIso()
  try {
    return await withTimeout(runner, timeoutMs, id)
  } catch (error) {
    return createFailedLayer(id, startedAt, error)
  }
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

    const publishRuntimeStatus = (state, extra = {}) => {
      const payload = { state, ...extra }
      window.__rezzervRegressionStatus = payload
      window.__REZZERV_REGRESSION_STATUS__ = payload
    }

    const finishRun = (nextStatus, nextReport, nextError = '') => {
      if (cancelled) return
      setReport(nextReport)
      setError(nextError)
      setStatus(nextStatus)
      window.__REZZERV_REGRESSION_RESULT__ = nextReport
      publishRuntimeStatus(nextStatus === 'completed' ? 'completed' : 'failed', {
        currentLayer: null,
        finishedAt: nowIso(),
        error: nextError || '',
        overallStatus: nextReport?.overall_status || (nextStatus === 'completed' ? 'passed' : 'failed'),
      })
    }

    async function run() {
      const startedAt = nowIso()
      setStatus('running')
      setError('')
      publishRuntimeStatus('running', { currentLayer: 'bootstrap', startedAt })
      try {
        const runPromise = (async () => {
          const layers = []
          publishRuntimeStatus('running', { currentLayer: 'api-almost-out-self-test', startedAt })
          layers.push(await runLayerSafely('api-almost-out-self-test', () => runApiAlmostOutSelfTestLayer()))
          publishRuntimeStatus('running', { currentLayer: 'layer1', startedAt })
          layers.push(await runLayerSafely('layer1', () => runLayerSuite('layer1', runLayer1Tests, runLayer1RegressionTests)))
          publishRuntimeStatus('running', { currentLayer: 'layer2', startedAt })
          layers.push(await runLayerSafely('layer2', () => runLayerSuite('layer2', runLayer2Tests, runLayer2RouteTests)))
          publishRuntimeStatus('running', { currentLayer: 'layer3', startedAt })
          layers.push(await runLayerSafely('layer3', () => runLayerSuite('layer3', runLayer3Tests, runLayer3StyleguideTests)))
          const overallStatus = layers.some((layer) => layer.status !== 'passed') ? 'failed' : 'passed'
          const nextReport = { version: getRezzervVersionTag(), started_at: startedAt, finished_at: nowIso(), overall_status: overallStatus, layers, summary_text: '' }
          nextReport.summary_text = toSummary(nextReport)
          return nextReport
        })()

        const nextReport = await withTimeout(() => runPromise, RUNNER_TIMEOUT_MS, 'regression-runner')
        finishRun(nextReport.overall_status === 'passed' ? 'completed' : 'failed', nextReport, nextReport.fatal_error || '')
      } catch (runError) {
        const failedReport = { version: getRezzervVersionTag(), started_at: startedAt, finished_at: nowIso(), overall_status: 'failed', layers: report?.layers || [], summary_text: '', fatal_error: normalizeLayerError(runError, 'Onbekende regressiefout') }
        failedReport.summary_text = toSummary(failedReport)
        finishRun('failed', failedReport, failedReport.fatal_error)
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
