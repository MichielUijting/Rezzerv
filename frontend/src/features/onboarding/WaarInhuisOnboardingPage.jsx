import { useState } from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { BooleanRadioChoices, ChoiceSummary, yesNo } from './OnboardingChoiceControls.jsx'

export default function WaarInhuisOnboardingPage({ onSubmit, saving = false, error = '' }) {
  const [unpacking, setUnpacking] = useState(false)
  const [receiptProcessing, setReceiptProcessing] = useState(false)
  const [almostOut, setAlmostOut] = useState(false)

  function finish() {
    onSubmit?.({
      unpacking_enabled: unpacking,
      receipt_processing_enabled: receiptProcessing,
      almost_out_enabled: almostOut,
    })
  }

  return (
    <div className="rz-form" data-testid="onboarding-waar-inhuis-follow-up">
      <div>
        <h1 style={{ marginTop: 0 }}>Waar Inhuis</h1>
        <p>
          Kies hier alleen hoe je Waar Inhuis wilt gebruiken. Hoofdlocaties en sublocaties beheer je na de inrichting via Instellingen → Locaties.
        </p>
      </div>

      <ChoiceSummary
        items={[
          { label: 'Locaties', value: 'Via Instellingen' },
          { label: 'Uitpakken', value: yesNo(unpacking, 'Nu', 'Later') },
          { label: 'Kassabonnen', value: yesNo(receiptProcessing, 'Nu', 'Later') },
          { label: 'Bijna op', value: yesNo(almostOut) },
        ]}
      />

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Direct starten met Uitpakken?</h2>
            <p style={{ marginBottom: 0 }}>
              Na een aankoop kan Inhuis je helpen spullen direct aan hun plek te koppelen.
            </p>
          </div>
          <BooleanRadioChoices
            name="Direct starten met Uitpakken"
            yesLabel="Nu"
            noLabel="Later"
            value={unpacking}
            onChange={setUnpacking}
            disabled={saving}
            testId="waar-inhuis-unpacking"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Kassabonnen gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Hiermee kun je nieuwe aankopen later sneller aan je overzicht toevoegen.
            </p>
          </div>
          <BooleanRadioChoices
            name="Kassabonnen gebruiken"
            yesLabel="Nu"
            noLabel="Later"
            value={receiptProcessing}
            onChange={setReceiptProcessing}
            disabled={saving}
            testId="waar-inhuis-receipts"
          />
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Ook Bijna op gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Activeer dit als je naast terugvinden ook wilt signaleren wat aangevuld moet worden.
            </p>
          </div>
          <BooleanRadioChoices
            name="Ook Bijna op gebruiken"
            value={almostOut}
            onChange={setAlmostOut}
            disabled={saving}
            testId="waar-inhuis-almost-out"
          />
        </div>
      </Card>

      <p style={{ marginBottom: 0 }} data-testid="waar-inhuis-locations-settings-hint">
        <strong>Locaties richt je na deze stap in via Instellingen → Locaties.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving}
        onClick={finish}
        data-testid="waar-inhuis-finish"
      >
        {saving ? 'Opslaan…' : 'Waar Inhuis instellen'}
      </Button>

      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
