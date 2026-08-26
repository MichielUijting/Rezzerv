import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const FIXTURE_ACTIONS = Object.freeze([
  {
    key: 'browser-reset',
    title: 'Browserregressiefixture opnieuw opbouwen',
    description: 'Verwijder de bestaande browserregressiefixture in de vaste demo-testomgeving en bouw de deterministische dataset opnieuw op.',
    endpoint: '/api/testing/fixtures/browser-regression/reset',
    confirmLabel: 'Browserfixture opnieuw opbouwen',
    warning: 'Deze actie verwijdert eerst bestaande browserregressie-testdata in de vaste demo-fixtureomgeving.',
  },
  {
    key: 'inventory-ensure',
    title: 'Regressievoorraad garanderen',
    description: 'Maak de vaste regressievoorraad aan of herstel ontbrekende fixturedata voor de Rezzerv-testomgeving.',
    endpoint: '/api/testing/fixtures/inventory/ensure',
    confirmLabel: 'Regressievoorraad garanderen',
  },
  {
    key: 'receipt-layer1',
    title: 'Receipt layer-1 fixture genereren',
    description: 'Bouw de vaste kassabon-fixture voor de layer-1 regressietests opnieuw op.',
    endpoint: '/api/testing/fixtures/receipt-layer1/generate',
    confirmLabel: 'Layer-1 fixture genereren',
  },
  {
    key: 'seed-kassa',
    title: 'Kassa-regressiebonnen seeden',
    description: 'Seed de vaste kassabonbestanden en -records die door de kassa-regressietests worden gebruikt.',
    endpoint: '/api/testing/fixtures/receipts/seed-kassa',
    confirmLabel: 'Kassa-fixtures seeden',
  },
  {
    key: 'receipt-export',
    title: 'Receipt-exportfixture genereren',
    description: 'Genereer de vaste testdata voor receipt-exportregressie. Downloaden gebeurt niet vanuit deze beheerpagina.',
    endpoint: '/api/testing/fixtures/receipt-export/generate',
    confirmLabel: 'Exportfixture genereren',
  },
  {
    key: 'cleanup',
    title: 'Regressiefixturedata opruimen',
    description: 'Ruim de vaste regressievoorraad- en kassabonfixturedata van de testomgeving op.',
    endpoint: '/api/testing/fixtures/cleanup',
    confirmLabel: 'Fixturedata definitief opruimen',
    warning: 'Let op: dit is een destructieve testdata-actie. Bestaande regressiefixturedata wordt verwijderd.',
  },
])

async function runFixtureAction(endpoint) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Fixtureactie is mislukt (${response.status}).`)
  }
  return payload
}

function FixtureResult({ actionKey, result }) {
  if (!result) return null
  const status = result.status || (result.ok === true ? 'ok' : 'uitgevoerd')
  const batchId = result.latestBatchId || result.batchId || ''
  return (
    <div data-testid={`platform-test-fixtures-result-${actionKey}`}>
      <p>Resultaat: {String(status)}</p>
      {result.dataset ? <p>Dataset: {String(result.dataset)}</p> : null}
      {result.household_id ? <p>Fixturedoel: {String(result.household_id)}</p> : null}
      {batchId ? <p>Fixturebatch: {String(batchId)}</p> : null}
      {result.message ? <p>{String(result.message)}</p> : null}
    </div>
  )
}

export default function PlatformTestFixturesPage() {
  const [confirming, setConfirming] = React.useState('')
  const [running, setRunning] = React.useState('')
  const [results, setResults] = React.useState({})
  const [errors, setErrors] = React.useState({})

  async function execute(action) {
    setRunning(action.key)
    setConfirming('')
    setErrors((current) => ({ ...current, [action.key]: '' }))
    try {
      const payload = await runFixtureAction(action.endpoint)
      setResults((current) => ({ ...current, [action.key]: payload }))
    } catch (error) {
      setResults((current) => ({ ...current, [action.key]: null }))
      setErrors((current) => ({ ...current, [action.key]: error?.message || 'Fixtureactie is mislukt.' }))
    } finally {
      setRunning('')
    }
  }

  return (
    <div className="rz-screen" data-testid="platform-test-fixtures-page">
      <Header title="Testfixtures" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformbrede regressiefixtures</h2>
            <p>Beheer uitsluitend de vaste Rezzerv-regressiefixturedata waarvoor je expliciet bent geautoriseerd.</p>
            <p>Deze pagina kiest geen huishoudcontext. Household-gerichte diagnostiek is hier bewust niet beschikbaar.</p>
            <p>De receipt-exportdownload is hier eveneens niet beschikbaar, omdat die route zonder identifiers zelf testdata kan genereren.</p>

            {FIXTURE_ACTIONS.map((action) => (
              <div key={action.key} data-testid={`platform-test-fixtures-action-${action.key}`}>
                <Card className="rz-card-home">
                  <h3>{action.title}</h3>
                  <p>{action.description}</p>
                  {action.warning ? <p>{action.warning}</p> : null}
                  {errors[action.key] ? <p role="alert">{errors[action.key]}</p> : null}
                  <FixtureResult actionKey={action.key} result={results[action.key]} />

                  {confirming === action.key ? (
                    <div data-testid={`platform-test-fixtures-confirm-${action.key}`}>
                      <p>Bevestig dat je deze platformbrede fixturemutatie wilt uitvoeren.</p>
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
