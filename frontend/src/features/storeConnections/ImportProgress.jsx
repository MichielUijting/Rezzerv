// Shared, accessible progress presentation for supported digital receipt imports.
// Totals are shown only when the provider has supplied a trustworthy count.
export default function ImportProgress({ store, phase, message, processed, total, counts, testId }) {
  if (!message && !phase) return null
  const hasTotal = Number.isSafeInteger(total) && total >= 0
  const hasProcessed = Number.isSafeInteger(processed) && processed >= 0
  const fraction = hasTotal && total > 0 && hasProcessed ? Math.min(1, processed / total) : null
  const headings = {
    waiting: 'Wachten op verbinding',
    fetching: 'Bonnen ophalen',
    validating: 'Bonnen controleren',
    importing: 'Bonnen verwerken',
    completed: 'Afgerond',
    failed: 'Mislukt',
  }
  return (
    <div className="rz-inline-feedback" role="status" aria-live="polite" data-testid={testId} style={{ display: 'grid', gap: 6 }}>
      <strong>{store} — {headings[phase] || 'Importstatus'}</strong>
      {hasTotal && hasProcessed ? (
        <div data-testid={testId + '-counter'}>{processed} van {total} bonnen verwerkt</div>
      ) : hasProcessed ? (
        <div data-testid={testId + '-counter'}>{processed} bonnen verwerkt (totaal nog onbekend)</div>
      ) : null}
      {fraction !== null ? (
        <progress value={processed} max={total} aria-label={store + ': bonnen verwerkt'} style={{ width: '100%' }} />
      ) : null}
      {message ? <div>{message}</div> : null}
      {counts ? (
        <div>{counts.new || 0} nieuw · {counts.known || 0} bekend · {counts.refreshed || 0} bijgewerkt · {counts.failed || 0} mislukt</div>
      ) : null}
    </div>
  )
}
