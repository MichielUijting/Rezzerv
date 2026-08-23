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

export default function InhuisHalenOnboardingPage({ onSubmit, saving = false, error = '' }) {
  const [simpleInventory, setSimpleInventory] = useState(true)
  const [almostOutNotifications, setAlmostOutNotifications] = useState(false)
  const [receiptProcessing, setReceiptProcessing] = useState(false)
  const [recipes, setRecipes] = useState(false)

  function changeSimpleInventory(enabled) {
    setSimpleInventory(enabled)
    if (!enabled) setAlmostOutNotifications(false)
  }

  function finish() {
    onSubmit?.({
      simple_inventory_enabled: simpleInventory,
      almost_out_notifications_enabled: almostOutNotifications,
      receipt_processing_enabled: receiptProcessing,
      recipes_enabled: recipes,
    })
  }

  return (
    <div className="rz-form" data-testid="onboarding-inhuis-halen-follow-up">
      <div>
        <h1 style={{ marginTop: 0 }}>Inhuis halen</h1>
        <p>
          Stel alleen in wat je nu nodig hebt. Exacte locaties zijn voor deze manier van werken niet nodig.
        </p>
      </div>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Eenvoudige voorraad gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Hiermee kan Inhuis helpen bepalen wat bijna op is. Dit staat standaard aan.
            </p>
          </div>
          <ChoiceButtons
            value={simpleInventory}
            onChange={changeSimpleInventory}
            testId="inhuis-halen-simple-inventory"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Meldingen wanneer iets bijna op is?</h2>
            <p style={{ marginBottom: 0 }}>
              Je kunt dit later altijd aanpassen bij de relevante instellingen.
            </p>
          </div>
          <ChoiceButtons
            value={almostOutNotifications}
            onChange={setAlmostOutNotifications}
            disabled={!simpleInventory}
            testId="inhuis-halen-almost-out-notifications"
          />
          {!simpleInventory ? (
            <small>Bijna-op meldingen worden beschikbaar als je eenvoudige voorraad gebruikt.</small>
          ) : null}
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Aankopen via kassabonnen verwerken?</h2>
            <p style={{ marginBottom: 0 }}>
              Kies Nu als je kassabonnen vanaf de start wilt gebruiken, of Later om dit nog niet te activeren.
            </p>
          </div>
          <ChoiceButtons
            yesLabel="Nu"
            noLabel="Later"
            value={receiptProcessing}
            onChange={setReceiptProcessing}
            testId="inhuis-halen-receipts"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Gerechten gebruiken als inspiratie?</h2>
            <p style={{ marginBottom: 0 }}>
              Gerechten kunnen later helpen om van inspiratie naar boodschappen te gaan.
            </p>
          </div>
          <ChoiceButtons
            yesLabel="Nu"
            noLabel="Later"
            value={recipes}
            onChange={setRecipes}
            testId="inhuis-halen-recipes"
          />
        </div>
      </Card>

      <p style={{ marginBottom: 0 }}>
        <strong>Je kunt deze mogelijkheden later uitbreiden of aanpassen.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving}
        onClick={finish}
        data-testid="inhuis-halen-finish"
      >
        {saving ? 'Opslaan…' : 'Inhuis halen instellen'}
      </Button>

      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
