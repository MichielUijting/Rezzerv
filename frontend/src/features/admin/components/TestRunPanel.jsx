import Button from '../../../ui/Button'

export default function TestRunPanel({ isRunning, onRunLayer1, onRunLayer2, onRunLayer3, onViewReport, showSuiteNotice = true }) {
  return (
    <div>
      {showSuiteNotice ? (
        <div className="rz-admin-inline-note" data-testid="regression-suite-banner">Leidend: laag 1 / laag 2 / laag 3.</div>
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
      <Button variant="secondary" onClick={onViewReport} disabled={isRunning === true ? false : false}>
        Laatste testrapport bekijken
      </Button>
      </div>
    </div>
  )
}
