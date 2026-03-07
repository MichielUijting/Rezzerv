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
    default:
      return 'Nog niet gestart'
  }
}

function typeLabel(type) {
  if (type === 'smoke') return 'Smoke test'
  if (type === 'regression') return 'Volledige regressietest'
  return 'Nog geen test'
}

export default function TestStatusCard({ status }) {
  return (
    <div className="rz-admin-status-card">
      <h4 className="rz-admin-status-title">Laatste teststatus</h4>
      <div className="rz-admin-stats">
        <div>Laatste test: {typeLabel(status?.test_type)}</div>
        <div>Status: {statusLabel(status?.status)}</div>
        <div>Laatste run: {formatDateTime(status?.last_run_at)}</div>
        <div>Resultaat: {status?.passed_count || 0} geslaagd / {status?.failed_count || 0} gefaald</div>
        {status?.last_error ? <div>Laatste fout: {status.last_error}</div> : null}
      </div>
    </div>
  )
}
