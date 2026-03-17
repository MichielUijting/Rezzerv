import Button from '../../../ui/Button'

export default function TestRunPanel({ isRunning, onRunSmoke, onRunLayer1, onRunLayer2, onRunLayer3, onRunRegression, onViewReport, showLegacyWarning = true }) {
  return (
    <div>
      {showLegacyWarning ? (
        <div className="rz-admin-inline-note" data-testid="legacy-suite-banner">Leidend: laag 1 / laag 2 / laag 3. Oude regressiesuite is alleen nog legacy referentie en diagnosehulp.</div>
      ) : null}
      <div className="rz-admin-actions">
      <Button variant="primary" onClick={onRunSmoke} disabled={isRunning}>
        Smoke test uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunLayer1} disabled={isRunning}>
        Laag-1 kernregressietest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunLayer2} disabled={isRunning}>
        Laag-2 route-/schermtest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunLayer3} disabled={isRunning}>
        Laag-3 UI/styleguide-test uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunRegression} disabled={isRunning}>
        Volledige regressietest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onViewReport} disabled={isRunning === true ? false : false}>
        Laatste testrapport bekijken
      </Button>
      </div>
    </div>
  )
}
