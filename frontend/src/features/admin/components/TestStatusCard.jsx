function formatDateTime(value) {
  if (!value) return 'Nog geen test uitgevoerd'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('nl-NL')
}

function statusLabel(status) {
  switch (status) {
    case 'running':
      return 'Bezig'
    case 'passed':
      return 'Geslaagd'
    case 'failed':
      return 'Gefaald'
    case 'blocked':
      return 'Geblokkeerd'
    case 'skipped':
      return 'Overgeslagen'
    default:
      return 'Nog niet gestart'
  }
}

function typeLabel(type) {
  if (type === 'layer1') return 'Laag-1 kernregressietest (leidend)'
  if (type === 'layer2') return 'Laag-2 route-/schermtest (leidend)'
  if (type === 'layer3') return 'Laag-3 UI/styleguide-test (leidend)'
  if (type === 'regression_all') return 'Regressietest alles (leidend)'
  if (type === 'parsing_baseline') return 'Parsing-baseline kassabonnen'
  return 'Nog geen test'
}

export default function TestStatusCard({ status, progress }) {
  return (
    <div className="rz-admin-status-card" data-testid="test-status-card">
      <h4 className="rz-admin-status-title">Laatste teststatus</h4>
      <div className="rz-admin-stats">
        <div>Actieve regressiesuite: laag 1 / laag 2 / laag 3</div>
        <div>Laatste test: {typeLabel(status?.test_type)}</div>
        <div>Status: {statusLabel(status?.status)}</div>
        <div>Laatste run: {formatDateTime(status?.last_run_at)}</div>
        <div>Resultaat: {status?.passed_count || 0} geslaagd / {status?.failed_count || 0} gefaald</div>
        {status?.last_error ? <div>Laatste fout: {status.last_error}</div> : null}
        {progress?.activeScenario ? <div>Actief scenario: {progress.activeScenario}</div> : null}
        {progress?.activeStep ? <div>Actieve stap: {progress.activeStep}</div> : null}
        {progress?.completedScenario ? <div>Laatst afgerond scenario: {progress.completedScenario}</div> : null}
        {progress?.lastError && !status?.last_error ? <div>Lopende foutcontext: {progress.lastError}</div> : null}
        {progress?.failureCategory ? <div>Failure-type: {progress.failureCategory}</div> : null}
        {progress?.failureRationale ? <div>Analyse: {progress.failureRationale}</div> : null}
        {progress?.failureSuggestedAction ? <div>Advies: {progress.failureSuggestedAction}</div> : null}
      </div>
    </div>
  )
}
