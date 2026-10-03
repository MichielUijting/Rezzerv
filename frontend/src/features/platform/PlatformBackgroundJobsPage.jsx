import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const BACKGROUND_ACTIONS = Object.freeze([
  {
    key: 'kassa-smoke',
    title: 'Kassa releasecontrole uitvoeren',
    description: 'Start de vaste Kassa smoke-baseline met één representatieve kassabon per ondersteunde winkelketen.',
    endpoint: '/api/admin/kassa-smoke/run',
    confirmLabel: 'Kassa releasecontrole starten',
    asynchronous: true,
  },
  {
    key: 'kassa-regression',
    title: 'Kassa inleesregressie uitvoeren',
    description: 'Start de volledige vaste Kassa inleesbaseline op de meegeleverde regressiekassabonnen.',
    endpoint: '/api/admin/kassa-regression/run',
    confirmLabel: 'Kassa inleesregressie starten',
    asynchronous: true,
  },
  {
    key: 'parsing-fixtures',
    title: 'Parsing-fixture regressie uitvoeren',
    description: 'Voer de server-side parsingbaseline uit op de vaste kassabonfixtures.',
    endpoint: '/api/testing/regression/parsing-fixtures/run',
    confirmLabel: 'Fixture-regressie starten',
  },
  {
    key: 'parsing-raw',
    title: 'Raw parsing regressie uitvoeren',
    description: 'Voer de server-side parsingbaseline uit op de vaste raw kassabonbestanden.',
    endpoint: '/api/testing/regression/parsing-raw/run',
    confirmLabel: 'Raw regressie starten',
  },
])

async function runBackgroundAction(endpoint) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Achtergrondtaak is mislukt (${response.status}).`)
  }
  return payload
}

function BackgroundResult({ actionKey, report }) {
  if (!report) return null
  if (Object.prototype.hasOwnProperty.call(report, 'progress_total')) {
    return (
      <div data-testid={`platform-background-jobs-result-${actionKey}`}>
        <p>Status: {String(report.status || 'gestart')}</p>
        <p>Voortgang: {String(report.progress_current || 0)} / {String(report.progress_total || 0)}</p>
        {report.message ? <p>{String(report.message)}</p> : null}
      </div>
    )
  }
  const results = Array.isArray(report.results) ? report.results : []
  const passed = results.filter((item) => item?.status === 'passed').length
  const failed = results.filter((item) => item?.status === 'failed').length
  const blocked = results.filter((item) => item?.status === 'blocked').length

  return (
    <div data-testid={`platform-background-jobs-result-${actionKey}`}>
      <p>Taaktype: {String(report.test_type || 'onbekend')}</p>
      <p>Controles: {results.length}</p>
      <p>Geslaagd: {passed}</p>
      <p>Mislukt: {failed}</p>
      <p>Geblokkeerd: {blocked}</p>
      {report.last_run_at ? <p>Afgerond: {String(report.last_run_at)}</p> : null}
    </div>
  )
}

export default function PlatformBackgroundJobsPage() {
  const [confirming, setConfirming] = React.useState('')
  const [running, setRunning] = React.useState('')
  const [results, setResults] = React.useState({})
  const [errors, setErrors] = React.useState({})

  async function execute(action) {
    setRunning(action.key)
    setConfirming('')
    setErrors((current) => ({ ...current, [action.key]: '' }))
    try {
      const payload = await runBackgroundAction(action.endpoint)
      setResults((current) => ({ ...current, [action.key]: payload }))
    } catch (error) {
      setResults((current) => ({ ...current, [action.key]: null }))
      setErrors((current) => ({ ...current, [action.key]: error?.message || 'Achtergrondtaak is mislukt.' }))
    } finally {
      setRunning('')
    }
  }

  return (
    <div className="rz-screen" data-testid="platform-background-jobs-page">
      <Header title="Achtergrondtaken" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Technische regressietaken</h2>
            <p>Start uitsluitend zelfstandig uitvoerbare server-side taken waarvoor je expliciet bent geautoriseerd.</p>
            <p>Zelfstandig uitvoerbare Kassa- en parsingregressies kunnen hier worden gestart. Externe layer-startmarkers blijven bewust buiten deze beheerpagina.</p>
            <p>Het completion-endpoint is een interne callback en is geen beheeractie.</p>
            <p>Status en historie vallen onder Diagnostiek en worden op deze pagina niet gelezen zonder <code>platform.diagnostics.view</code>.</p>
            <p>Parsingtaken worden binnen de serverrequest uitgevoerd. De Kassa-controles starten als server-side achtergrondtaak; de actuele voortgang is daarna onder Diagnostiek zichtbaar.</p>

            {BACKGROUND_ACTIONS.map((action) => (
              <div key={action.key} data-testid={`platform-background-jobs-action-${action.key}`}>
                <Card className="rz-card-home">
                  <h3>{action.title}</h3>
                  <p>{action.description}</p>

                  {errors[action.key] ? <p role="alert">{errors[action.key]}</p> : null}
                  <BackgroundResult actionKey={action.key} report={results[action.key]} />

                  {confirming === action.key ? (
                    <div data-testid={`platform-background-jobs-confirm-${action.key}`}>
                      <p>Bevestig dat je deze technische regressietaak wilt uitvoeren.</p>
                      <Button type="button" onClick={() => execute(action)} disabled={Boolean(running)}>
                        {action.confirmLabel}
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => setConfirming('')} disabled={Boolean(running)}>
                        Annuleren
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setConfirming(action.key)}
                      disabled={Boolean(running)}
                    >
                      {running === action.key ? 'Bezig…' : action.title}
                    </Button>
                  )}
                </Card>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  )
}
