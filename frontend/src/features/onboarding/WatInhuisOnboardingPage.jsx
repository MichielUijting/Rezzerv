import { useState } from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'

function ChoiceButtons({ yesLabel = 'Ja', noLabel = 'Nee', value, onChange, disabled = false, testId }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <Button
        type="button"
        variant={value ? 'primary' : 'secondary'}
        disabled={disabled}
        onClick={() => onChange(true)}
        data-testid={`${testId}-yes`}
      >
        {yesLabel}
      </Button>
      <Button
        type="button"
        variant={!value ? 'primary' : 'secondary'}
        disabled={disabled}
        onClick={() => onChange(false)}
        data-testid={`${testId}-no`}
      >
        {noLabel}
      </Button>
    </div>
  )
}

function TrackingLevelButtons({ value, onChange, disabled = false }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <Button
        type="button"
        variant={value === 'presence' ? 'primary' : 'secondary'}
        disabled={disabled}
        onClick={() => onChange('presence')}
        data-testid="wat-inhuis-tracking-presence"
      >
        Alleen aanwezigheid
      </Button>
      <Button
        type="button"
        variant={value === 'quantity' ? 'primary' : 'secondary'}
        disabled={disabled}
        onClick={() => onChange('quantity')}
        data-testid="wat-inhuis-tracking-quantity"
      >
        Ook aantallen
      </Button>
    </div>
  )
}

export default function WatInhuisOnboardingPage({ onSubmit, saving = false, error = '' }) {
  const [inventoryTrackingLevel, setInventoryTrackingLevel] = useState('presence')
  const [globalLocations, setGlobalLocations] = useState(false)
  const [almostOut, setAlmostOut] = useState(false)
  const [shopping, setShopping] = useState(false)

  function finish() {
    onSubmit?.({
      inventory_tracking_level: inventoryTrackingLevel,
      global_locations_enabled: globalLocations,
      almost_out_enabled: almostOut,
      shopping_enabled: shopping,
    })
  }

  return (
    <div className="rz-form" data-testid="onboarding-wat-inhuis-follow-up">
      <div>
        <h1 style={{ marginTop: 0 }}>Wat Inhuis</h1>
        <p>
          Kies hoeveel detail je nu wilt bijhouden. Exacte opslagplekken zijn niet nodig.
        </p>
      </div>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Wat wil je bijhouden?</h2>
            <p style={{ marginBottom: 0 }}>
              Je kunt alleen vastleggen óf je iets hebt, of ook hoeveel je ervan hebt.
            </p>
          </div>
          <TrackingLevelButtons
            value={inventoryTrackingLevel}
            onChange={setInventoryTrackingLevel}
            disabled={saving}
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Globale plekken gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Denk aan Keuken, Garage of Badkamer. Je hoeft geen kasten, planken of bakken vast te leggen.
            </p>
          </div>
          <ChoiceButtons
            value={globalLocations}
            onChange={setGlobalLocations}
            disabled={saving}
            testId="wat-inhuis-global-locations"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Bijna op gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Hiermee kun je vanuit je overzicht ook bijhouden wat aangevuld moet worden.
            </p>
          </div>
          <ChoiceButtons
            value={almostOut}
            onChange={setAlmostOut}
            disabled={saving}
            testId="wat-inhuis-almost-out"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Vanuit je overzicht ook winkelen?</h2>
            <p style={{ marginBottom: 0 }}>
              Kies Nu als je direct boodschappen wilt kunnen maken, of Later als je eerst alleen overzicht wilt.
            </p>
          </div>
          <ChoiceButtons
            yesLabel="Nu"
            noLabel="Later"
            value={shopping}
            onChange={setShopping}
            disabled={saving}
            testId="wat-inhuis-shopping"
          />
        </div>
      </Card>

      <p style={{ marginBottom: 0 }}>
        <strong>Je kunt later altijd meer detail of extra mogelijkheden toevoegen.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving}
        onClick={finish}
        data-testid="wat-inhuis-finish"
      >
        {saving ? 'Opslaan…' : 'Wat Inhuis instellen'}
      </Button>

      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
