import { useState } from 'react'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'

export default function QuickStartOnboardingPage({
  initialHouseholdName = 'Mijn huishouden',
  onSubmit,
  saving = false,
  error = '',
}) {
  const [householdName, setHouseholdName] = useState(initialHouseholdName || 'Mijn huishouden')

  function submit(event) {
    event.preventDefault()
    const name = householdName.trim()
    if (name) onSubmit?.({ household_name: name })
  }

  return (
    <form className="rz-form" data-testid="onboarding-quick-start" onSubmit={submit}>
      <h1 style={{ margin: 0 }}>Start Inhuis</h1>
      <Input
        label="Huishouden"
        value={householdName}
        onChange={(event) => setHouseholdName(event.target.value)}
        maxLength={120}
        disabled={saving}
        required
        data-testid="onboarding-quick-start-household"
      />
      <p style={{ margin: 0 }} data-testid="onboarding-quick-start-defaults">
        Standaard: Wat Inhuis · Aantallen · Alleen.
      </p>
      <Button type="submit" variant="primary" disabled={saving} data-testid="onboarding-quick-start-submit">
        {saving ? 'Bezig…' : 'Start Inhuis'}
      </Button>
      {error ? <div className="rz-alert">{error}</div> : null}
    </form>
  )
}
