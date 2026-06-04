import React, { useEffect, useState } from 'react'
import Button from '../../../ui/Button'

const KASSA_SMOKE_COUNT = 6

function getAuthHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function readJsonOrText(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text.slice(0, 1200), non_json_response: true }
  }
}

function statusLabel(status) {
  if (status === 'passed') return 'Geslaagd'
  if (status === 'running') return 'Bezig'
  if (status === 'blocked') return 'Geblokkeerd'
  if (status === 'failed') return 'Gefaald'
  if (status === 'missing') return 'Ontbreekt'
  return status || 'Onbekend'
}

function summarizeError(data, fallback) {
  if (!data) return fallback
  if (Array.isArray(data.blocking_issues) && data.blocking_issues.length) {
    return `Kassa releasecontrole geblokkeerd: ${data.blocking_issues[0]}`
  }
  if (data.detail) return `Kassa releasecontrole kon niet worden uitgevoerd: ${data.detail}`
  if (data.message) return `Kassa releasecontrole kon niet worden uitgevoerd: ${data.message}`
  return fallback
}

export default function KassaSmokePanel({ onMessage }) {
  const [isRunning, setIsRunning] = useState(false)
  const [job, setJob] = useState(null)
  const [report, setReport] = useState(null)

  async function fetchSmokeStatus() {
    const res = await fetch('/api/admin/kassa-smoke/status', {
      headers: { Accept: 'application/json', ...getAuthHeaders() },
    })
    const data = await readJsonOrText(res)
    if (!res.ok) {
      onMessage?.(summarizeError(data, `Kassa releasestatus kon niet worden opgehaald. HTTP ${res.status}`))
      return null
    }
    setJob(data)
    if (data?.report) setReport(data.report)
    setIsRunning(data?.status === 'running')
    return data
  }

  useEffect(() => {
    fetchSmokeStatus().catch(() => {})
  }, [])

  useEffect(() => {
    if (!isRunning) return undefined
    const timer = window.setInterval(() => {
      fetchSmokeStatus().catch((error) => {
        onMessage?.(`Kassa releasestatus kon niet worden opgehaald: ${error?.message || 'onbekende fout'}`)
      })
    }, 1500)
    return () => window.clearInterval(timer)
  }, [isRunning])

  async function handleRunSmoke() {
    onMessage?.('')
    setReport(null)
    setIsRunning(true)
    try {
      const res = await fetch('/api/admin/kassa-smoke/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: '{}',
      })
      const data = await readJsonOrText(res)
      if (!res.ok) {
        setIsRunning(false)
        setJob(data && typeof data === 'object' ? data : null)
        onMessage?.(summarizeError(data, `Kassa releasecontrole kon niet worden gestart. HTTP ${res.status}`))
        return
      }
      setJob(data)
      if (data?.report) setReport(data.report)
      setIsRunning(data?.status === 'running')
      onMessage?.(data?.status === 'running' ? 'Kassa releasecontrole baseline V8 gestart.' : 'Kassa releasecontrole bijgewerkt.')
    } catch (error) {
      setIsRunning(false)
      onMessage?.(`Kassa releasecontrole kon niet worden gestart: ${error?.message || 'onbekende frontend/netwerkfout'}`)
    }
  }

  const progressCurrent = Number(job?.progress_current || 0)
  const progressTotal = Number(job?.progress_total || KASSA_SMOKE_COUNT)
  const progressPercent = progressTotal > 0 ? Math.round((progressCurrent / progressTotal) * 100) : 0

  return (
    <div className="rz-admin-panel" data-testid="kassa-smoke-panel">
      <h3>Kassa releasecontrole</h3>
      <p className="rz-admin-muted">
        Voert baseline V8 uit met 1 vaste testkassabon per winkelketen, inclusief Picnic. Release-gate: 6 getest, 6 geslaagd, 0 gefaald, 0 geblokkeerd. Datum/tijd wordt nooit gevalideerd.
      </p>
      <div className="rz-admin-actions">
        <Button variant="secondary" onClick={handleRunSmoke} disabled={isRunning} data-testid="run-kassa-smoke-button">
          {isRunning ? 'Kassa releasecontrole draait…' : 'Kassa releasecontrole uitvoeren'}
        </Button>
      </div>

      {job ? (
        <div className="rz-admin-report" data-testid="kassa-smoke-progress">
          <h4 className="rz-admin-status-title">Voortgang kassa releasecontrole</h4>
          <div className="rz-admin-report-meta">
            <div>Status: {statusLabel(job.status)}</div>
            <div>Voortgang: bon {progressCurrent} van {progressTotal}</div>
            <div>Percentage: {progressPercent}%</div>
            <div>Huidige bon: {job.current_case_id || '-'}</div>
            <div>Bestand: {job.current_filename || '-'}</div>
            <div>Melding: {job.message || '-'}</div>
          </div>
        </div>
      ) : null}

      {report ? (
        <div className="rz-admin-report" data-testid="kassa-smoke-report">
          <h4 className="rz-admin-status-title">Laatste kassa releasecontrole</h4>
          <div className="rz-admin-report-meta">
            <div>Status: {statusLabel(report.status)}</div>
            <div>Uitgevoerd: {report.ran_at || 'Onbekend'}</div>
            <div>Testbron: {report.acceptance_basis || 'Onbekend'}</div>
            <div>Vereist: {report.summary?.required_receipt_count || KASSA_SMOKE_COUNT}</div>
            <div>Getest: {report.summary?.tested_receipt_count || 0}</div>
            <div>Geslaagd: {report.summary?.passed_count || 0}</div>
            <div>Gefaald: {report.summary?.failed_count || 0}</div>
            <div>Geblokkeerd: {report.summary?.blocked_count || 0}</div>
          </div>
          {(report.blocking_issues || []).length ? (
            <div className="rz-admin-report-list">
              {(report.blocking_issues || []).map((issue) => (
                <div key={issue} className="rz-admin-report-row rz-admin-report-row--failed">
                  <div className="rz-admin-report-main"><span>{issue}</span><span>Geblokkeerd</span></div>
                </div>
              ))}
            </div>
          ) : null}
          <div className="rz-admin-report-list">
            {(report.chains || []).map((item) => (
              <div key={item.chain} className={`rz-admin-report-row rz-admin-report-row--${item.status === 'passed' ? 'passed' : 'failed'}`}>
                <div className="rz-admin-report-main">
                  <span>{item.chain}</span>
                  <span>{statusLabel(item.status)}</span>
                </div>
                <div className="rz-admin-report-meta-line">Bonnen: {item.receipt_count} · geslaagd {item.passed_count} · gefaald {item.failed_count}</div>
                {(item.failures || []).slice(0, 3).map((failure) => (
                  <div key={failure.case_id || failure.receipt_id || failure.filename} className="rz-admin-report-meta-line">{failure.case_id || failure.receipt_id || failure.filename}: {failure.error || 'onbekende fout'}</div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
