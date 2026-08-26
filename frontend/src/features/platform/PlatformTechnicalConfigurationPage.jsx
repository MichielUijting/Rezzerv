import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const TECHNICAL_ACTIONS = Object.freeze([
  {
    key: 'schema',
    title: 'Voorraadgroepschema initialiseren',
    description: 'Controleer en initialiseer de centrale technische tabellen voor voorraad- en productgroepen.',
    endpoint: '/api/admin/inventory/groups/ensure-schema',
    confirmLabel: 'Schema-initialisatie bevestigen',
  },
  {
    key: 'gpc-nl',
    title: 'GS1 GPC NL bijwerken',
    description: 'Importeer de actuele Nederlandse GS1 GPC-publicatie als centrale Rezzerv-referentiedata.',
    endpoint: '/api/admin/product-groups/import-gpc-nl',
    confirmLabel: 'GPC NL-import bevestigen',
  },
])

function displayValue(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

async function runTechnicalAction(endpoint) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Technische actie is mislukt (${response.status}).`)
  }
  return payload
}

function ActionResult({ actionKey, result }) {
  if (!result) return null
  if (actionKey === 'schema') {
    return (
      <div data-testid="platform-technical-result-schema">
        <p>Schema: {displayValue(result.schema)}</p>
        <p>Seed: {displayValue(result.seed)}</p>
        <p>Huishoudvoorraad gewijzigd: {result.mutates_inventory === false ? 'nee' : displayValue(result.mutates_inventory)}</p>
      </div>
    )
  }
  return (
    <div data-testid="platform-technical-result-gpc-nl">
      <p>Bronversie: {displayValue(result.source_version)}</p>
      <p>GPC bricks: {displayValue(result.total_bricks)}</p>
      <p>Families: {displayValue(result.total_families)}</p>
      <p>Classes: {displayValue(result.total_classes)}</p>
      <p>Nieuwe productgroepen: {displayValue(result.product_groups_created, '0')}</p>
      <p>Bijgewerkte productgroepen: {displayValue(result.product_groups_updated, '0')}</p>
      <p>Huishoudvoorraad gewijzigd: {result.mutates_inventory === false ? 'nee' : displayValue(result.mutates_inventory)}</p>
    </div>
  )
}

export default function PlatformTechnicalConfigurationPage() {
  const [confirming, setConfirming] = React.useState('')
  const [running, setRunning] = React.useState('')
  const [results, setResults] = React.useState({})
  const [errors, setErrors] = React.useState({})

  async function execute(action) {
    setRunning(action.key)
    setConfirming('')
    setErrors((current) => ({ ...current, [action.key]: '' }))
    try {
      const payload = await runTechnicalAction(action.endpoint)
      setResults((current) => ({ ...current, [action.key]: payload }))
    } catch (error) {
      setResults((current) => ({ ...current, [action.key]: null }))
      setErrors((current) => ({ ...current, [action.key]: error?.message || 'Technische actie is mislukt.' }))
    } finally {
      setRunning('')
    }
  }

  return (
    <div className="rz-screen" data-testid="platform-technical-configuration-page">
      <Header title="Technische configuratie" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformbrede technische configuratie</h2>
            <p>Voer uitsluitend centrale technische beheeracties uit waarvoor je expliciet bent geautoriseerd.</p>
            <p>Deze acties gebruiken geen huishoudcontext en wijzigen geen huishoudvoorraad.</p>
            <p>De legacy bundled GPC-import met admin-key is hier bewust niet beschikbaar.</p>

            {TECHNICAL_ACTIONS.map((action) => (
              <div key={action.key} data-testid={`platform-technical-action-${action.key}`}>
                <Card className="rz-card-home">
                  <h3>{action.title}</h3>
                  <p>{action.description}</p>

                  {errors[action.key] ? <p role="alert">{errors[action.key]}</p> : null}
                  <ActionResult actionKey={action.key} result={results[action.key]} />

                  {confirming === action.key ? (
                    <div data-testid={`platform-technical-confirm-${action.key}`}>
                      <p>Bevestig dat je deze platformbrede technische mutatie wilt uitvoeren.</p>
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
