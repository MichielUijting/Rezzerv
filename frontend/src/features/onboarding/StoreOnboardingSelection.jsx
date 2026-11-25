import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import './storeOnboardingSelection.css'

export const ONBOARDING_STORES = [
  { code: 'ah', label: 'Albert Heijn', mark: 'ah' },
  { code: 'jumbo', label: 'Jumbo', mark: 'J' },
  { code: 'lidl', label: 'Lidl', mark: 'L' },
]

const resultLabels = { success: 'Geslaagd', failed: 'Mislukt', pending: 'Nog te koppelen' }

export default function StoreOnboardingSelection({
  selected = [], results = {}, busy = false, onSelect, onStart, onLater, onRetry,
}) {
  const hasResults = Object.keys(results).length > 0
  const hasFailures = selected.some(code => results[code] === 'failed')
  const remaining = selected.filter(code => results[code] !== 'success')
  return (
    <Card className="rz-store-onboarding-card">
      <section className="rz-store-onboarding" data-testid="store-onboarding-selection">
        <h2>Met welke winkels wil je koppelen om je kassabonnen op te halen?</h2>
        <table className="rz-store-onboarding-table">
          <thead><tr><th scope="col">Winkel</th><th scope="col">Ja</th><th scope="col">Resultaat</th></tr></thead>
          <tbody>
            {ONBOARDING_STORES.map(({ code, label, mark }) => {
              const result = results[code]
              return (
                <tr key={code} data-result={result || 'neutral'} data-testid={'onboarding-store-row-' + code}>
                  <th scope="row"><span className="rz-store-onboarding-name"><span aria-hidden="true" className={`rz-store-onboarding-mark rz-store-onboarding-mark--${code}`} data-testid={`onboarding-store-mark-${code}`}>{mark}</span><span>{label}</span></span></th>
                  <td>
                    <label className="rz-store-onboarding-choice">
                      <input type="checkbox" aria-label={label + ' koppelen'} checked={selected.includes(code)}
                        disabled={busy || result === 'success'} onChange={event => onSelect(code, event.target.checked)}
                        data-testid={'onboarding-select-' + code} />
                      <span aria-hidden="true" className="rz-store-onboarding-circle">✓</span>
                    </label>
                  </td>
                  <td><span className="rz-store-onboarding-result" aria-live="polite">
                    {result === 'success' || result === 'failed' ? <span aria-hidden="true">{result === 'success' ? '✓' : '!'}</span> : null}
                    {resultLabels[result] || (selected.includes(code) ? 'Nog te koppelen' : 'Niet geselecteerd')}
                  </span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="rz-store-onboarding-actions">
          <Button type="button" variant="secondary" disabled={busy} onClick={onLater} data-testid="onboarding-stores-later">{hasResults ? 'Naar dashboard' : 'Later koppelen'}</Button>
          {remaining.length > 0 && <Button type="button" disabled={busy} onClick={hasResults ? onRetry : onStart} data-testid="onboarding-stores-start">{hasFailures ? 'Mislukte of overige winkels koppelen' : hasResults ? 'Overige winkels koppelen' : 'Geselecteerde winkels koppelen'}</Button>}
        </div>
      </section>
    </Card>
  )
}
