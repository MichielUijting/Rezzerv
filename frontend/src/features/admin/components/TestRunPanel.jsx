import { useState } from 'react'
import Button from '../../../ui/Button'

function getAuthHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function TestRunPanel({
  isRunning,
  onRunLayer1,
  onRunLayer2,
  onRunLayer3,
  onRunAll,
  onRunAlmostOutSelfTest,
  onViewReport,
  showSuiteNotice = true,
}) {
  const [cleanupMessage, setCleanupMessage] = useState('')
  const [isCleaningReceipts, setIsCleaningReceipts] = useState(false)

  async function handlePurgeDeletedReceipts() {
    setCleanupMessage('')
    const confirmed = window.confirm('Verwijderde kassabonnen definitief opschonen? Dit kan niet ongedaan worden gemaakt.')
    if (!confirmed) return
    setIsCleaningReceipts(true)
    try {
      const response = await fetch('/api/dev/receipts/purge-deleted', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({}),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        setCleanupMessage(data.detail || 'Opschonen verwijderde kassabonnen mislukt')
        return
      }
      setCleanupMessage(`Opschonen afgerond: ${data.purged_receipt_count || 0} bon(nen), ${data.purged_raw_receipt_count || 0} bronbestand(en).`)
    } catch {
      setCleanupMessage('Opschonen verwijderde kassabonnen kon niet worden uitgevoerd')
    } finally {
      setIsCleaningReceipts(false)
    }
  }

  return (
    <div>
      {showSuiteNotice ? (
        <div className="rz-admin-inline-note" data-testid="regression-suite-banner">Leidend: laag 1 / laag 2 / laag 3. Almost-out backend self-test is apart zichtbaar.</div>
      ) : null}
      <div className="rz-admin-actions">
      <Button variant="secondary" onClick={onRunLayer1} disabled={isRunning}>
        Laag-1 kernregressietest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunLayer2} disabled={isRunning}>
        Laag-2 route-/schermtest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunLayer3} disabled={isRunning}>
        Laag-3 UI/styleguide-test uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunAlmostOutSelfTest} disabled={isRunning} data-testid="run-almost-out-self-test-button">
        Almost-out backend self-test
      </Button>
      <Button variant="primary" onClick={onRunAll} disabled={isRunning} data-testid="run-all-regression-tests-button">
        Regressietest alles
      </Button>
      <Button variant="secondary" onClick={onViewReport} disabled={false}>
        Laatste testrapport bekijken
      </Button>
      </div>
      <div className="rz-admin-inline-note" style={{ marginTop: '12px' }}>
        <strong>Database opschonen</strong><br />
        Verwijdert alleen kassabonnen die al als verwijderd/gearchiveerd zijn gemarkeerd. Het inleesproces en de baseline blijven ongewijzigd.
      </div>
      <div className="rz-admin-actions" style={{ marginTop: '8px' }}>
        <Button variant="secondary" onClick={handlePurgeDeletedReceipts} disabled={isRunning || isCleaningReceipts} data-testid="purge-deleted-receipts-button">
          {isCleaningReceipts ? 'Opschonen…' : 'Verwijderde kassabonnen opschonen'}
        </Button>
      </div>
      {cleanupMessage ? <div className="rz-admin-message">{cleanupMessage}</div> : null}
    </div>
  )
}
