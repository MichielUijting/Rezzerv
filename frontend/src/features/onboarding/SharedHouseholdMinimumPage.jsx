import { useState } from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'

function UsageModeButton({ mode, activeMode, onChange, disabled, children, testId }) {
  return (
    <Button
      type="button"
      variant={activeMode === mode ? 'primary' : 'secondary'}
      disabled={disabled}
      onClick={() => onChange(mode)}
      data-testid={testId}
    >
      {children}
    </Button>
  )
}

export default function SharedHouseholdMinimumPage({
  initialHouseholdName = '',
  onSubmit,
  saving = false,
  error = '',
}) {
  const [householdName, setHouseholdName] = useState(String(initialHouseholdName || ''))
  const [usageMode, setUsageMode] = useState('')

  const canFinish = Boolean(String(householdName || '').trim() && usageMode)

  function finish() {
    if (!canFinish) return
    onSubmit?.({
      household_name: String(householdName || '').trim(),
      household_usage_mode: usageMode,
    })
  }

  return (
    <div className="rz-form" data-testid="onboarding-shared-household-minimum">
      <div>
        <h1 style={{ marginTop: 0 }}>Nog even je huishouden</h1>
        <p>
          Met deze twee gegevens maken we de gedeelde basis van Inhuis af.
        </p>
      </div>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Hoe heet je huishouden?</h2>
            <p style={{ marginBottom: 0 }}>
              Deze naam zie je terug bij je gedeelde huishoudcontext. Je kunt hem later wijzigen.
            </p>
          </div>
          <Input
            label="Naam huishouden"
            value={householdName}
            onChange={(event) => setHouseholdName(event.target.value)}
            disabled={saving}
            required
            maxLength={120}
            placeholder="Bijvoorbeeld Familie Jansen"
            data-testid="shared-household-name"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Gebruik je Inhuis alleen of samen?</h2>
            <p style={{ marginBottom: 0 }}>
              Dit bepaalt alleen of samen gebruiken en uitnodigen voor jouw huishouden relevant is.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <UsageModeButton
              mode="alone"
              activeMode={usageMode}
              onChange={setUsageMode}
              disabled={saving}
              testId="shared-household-usage-alone"
            >
              Alleen
            </UsageModeButton>
            <UsageModeButton
              mode="together"
              activeMode={usageMode}
              onChange={setUsageMode}
              disabled={saving}
              testId="shared-household-usage-together"
            >
              Samen
            </UsageModeButton>
          </div>
        </div>
      </Card>

      {usageMode === 'together' ? (
        <Card>
          <div className="rz-form" data-testid="shared-household-invite-deferred">
            <div>
              <h2 style={{ marginTop: 0 }}>Iemand uitnodigen</h2>
              <p style={{ marginBottom: 0 }}>
                Dat hoeft nu niet. Een echte uitnodiging moet veilig via een uitnodigingsmail en acceptatie verlopen. Je kunt daarom nu gewoon afronden en later iemand uitnodigen zodra die flow beschikbaar is.
              </p>
            </div>
            <strong>Uitnodigen: later</strong>
          </div>
        </Card>
      ) : null}

      <p style={{ marginBottom: 0 }}>
        <strong>Je kunt deze gegevens en mogelijkheden later verder aanpassen.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving || !canFinish}
        onClick={finish}
        data-testid="shared-household-finish"
      >
        {saving ? 'Opslaan…' : 'Onboarding afronden'}
      </Button>

      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
