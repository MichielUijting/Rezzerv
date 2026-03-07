import Button from '../../../ui/Button'

export default function TestRunPanel({ isRunning, onRunSmoke, onRunRegression, onViewReport }) {
  return (
    <div className="rz-admin-actions">
      <Button variant="primary" onClick={onRunSmoke} disabled={isRunning}>
        Smoke test uitvoeren
      </Button>
      <Button variant="secondary" onClick={onRunRegression} disabled={isRunning}>
        Volledige regressietest uitvoeren
      </Button>
      <Button variant="secondary" onClick={onViewReport} disabled={isRunning === true ? false : false}>
        Laatste testrapport bekijken
      </Button>
    </div>
  )
}
