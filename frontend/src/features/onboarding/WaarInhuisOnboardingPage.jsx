import { useMemo, useState } from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'

const PRESET_LOCATIONS = ['Keuken', 'Bijkeuken', 'Garage', 'Schuur', 'Zolder', 'Badkamer']

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

function normalizeName(value) {
  return String(value || '').trim().replace(/\s+/g, ' ')
}

export default function WaarInhuisOnboardingPage({ onSubmit, saving = false, error = '' }) {
  const [mainLocations, setMainLocations] = useState([])
  const [customLocation, setCustomLocation] = useState('')
  const [refineLocations, setRefineLocations] = useState(false)
  const [sublocations, setSublocations] = useState([])
  const [sublocationSpace, setSublocationSpace] = useState('')
  const [sublocationName, setSublocationName] = useState('')
  const [unpacking, setUnpacking] = useState(false)
  const [receiptProcessing, setReceiptProcessing] = useState(false)
  const [almostOut, setAlmostOut] = useState(false)
  const [localError, setLocalError] = useState('')

  const selectedKeys = useMemo(
    () => new Set(mainLocations.map((name) => name.toLocaleLowerCase())),
    [mainLocations],
  )

  function toggleLocation(name) {
    const normalized = normalizeName(name)
    const key = normalized.toLocaleLowerCase()
    setLocalError('')
    setMainLocations((current) => {
      const exists = current.some((item) => item.toLocaleLowerCase() === key)
      if (exists) {
        setSublocations((items) => items.filter(
          (item) => item.space_name.toLocaleLowerCase() !== key,
        ))
        return current.filter((item) => item.toLocaleLowerCase() !== key)
      }
      return [...current, normalized]
    })
  }

  function addCustomLocation() {
    const normalized = normalizeName(customLocation)
    if (!normalized) return
    if (selectedKeys.has(normalized.toLocaleLowerCase())) {
      setLocalError('Deze hoofdlocatie is al gekozen.')
      return
    }
    if (mainLocations.length >= 12) {
      setLocalError('Kies maximaal 12 hoofdlocaties tijdens de eerste inrichting.')
      return
    }
    setMainLocations((current) => [...current, normalized])
    setCustomLocation('')
    setLocalError('')
  }

  function changeRefineLocations(enabled) {
    setRefineLocations(enabled)
    setLocalError('')
    if (!enabled) {
      setSublocations([])
      setSublocationSpace('')
      setSublocationName('')
    }
  }

  function addSublocation() {
    const spaceName = normalizeName(sublocationSpace)
    const name = normalizeName(sublocationName)
    if (!spaceName || !name) {
      setLocalError('Kies een hoofdlocatie en geef de sublocatie een naam.')
      return
    }
    const duplicate = sublocations.some(
      (item) => item.space_name.toLocaleLowerCase() === spaceName.toLocaleLowerCase()
        && item.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
    )
    if (duplicate) {
      setLocalError('Deze sublocatie is al toegevoegd.')
      return
    }
    if (sublocations.length >= 30) {
      setLocalError('Voeg maximaal 30 sublocaties toe tijdens de eerste inrichting.')
      return
    }
    setSublocations((current) => [...current, { space_name: spaceName, name }])
    setSublocationName('')
    setLocalError('')
  }

  function finish() {
    if (!mainLocations.length) {
      setLocalError('Kies minimaal één hoofdlocatie.')
      return
    }
    onSubmit?.({
      main_locations: mainLocations,
      sublocations: refineLocations ? sublocations : [],
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
          Richt alleen de plekken in die je nu nodig hebt. Kasten, planken en bakken kun je later altijd verder verfijnen.
        </p>
      </div>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Welke hoofdlocaties wil je gebruiken?</h2>
            <p style={{ marginBottom: 0 }}>
              Kies één of meer plekken waar je spullen of voorraad bewaart.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {PRESET_LOCATIONS.map((name) => {
              const selected = selectedKeys.has(name.toLocaleLowerCase())
              return (
                <Button
                  key={name}
                  type="button"
                  variant={selected ? 'primary' : 'secondary'}
                  disabled={saving}
                  onClick={() => toggleLocation(name)}
                  data-testid={`waar-inhuis-location-${name.toLocaleLowerCase()}`}
                >
                  {name}
                </Button>
              )
            })}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              className="rz-input"
              value={customLocation}
              maxLength={120}
              disabled={saving}
              placeholder="Andere hoofdlocatie"
              onChange={(event) => setCustomLocation(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  addCustomLocation()
                }
              }}
              data-testid="waar-inhuis-custom-location-input"
            />
            <Button
              type="button"
              variant="secondary"
              disabled={saving || !normalizeName(customLocation)}
              onClick={addCustomLocation}
              data-testid="waar-inhuis-custom-location-add"
            >
              Toevoegen
            </Button>
          </div>
          {mainLocations.length ? (
            <small>Gekozen: {mainLocations.join(', ')}</small>
          ) : (
            <small>Kies minimaal één hoofdlocatie.</small>
          )}
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Locaties nu al verfijnen?</h2>
            <p style={{ marginBottom: 0 }}>
              Denk aan Voorraadkast, Koelkast, Kast links, Stelling of Lade 2. Dit mag ook later.
            </p>
          </div>
          <ChoiceButtons
            yesLabel="Nu verfijnen"
            noLabel="Later"
            value={refineLocations}
            onChange={changeRefineLocations}
            disabled={saving || !mainLocations.length}
            testId="waar-inhuis-refine-locations"
          />
          {refineLocations && mainLocations.length ? (
            <div className="rz-form">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <select
                  className="rz-input"
                  value={sublocationSpace}
                  disabled={saving}
                  onChange={(event) => setSublocationSpace(event.target.value)}
                  data-testid="waar-inhuis-sublocation-space"
                >
                  <option value="">Kies hoofdlocatie</option>
                  {mainLocations.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
                <input
                  className="rz-input"
                  value={sublocationName}
                  maxLength={120}
                  disabled={saving}
                  placeholder="Naam sublocatie"
                  onChange={(event) => setSublocationName(event.target.value)}
                  data-testid="waar-inhuis-sublocation-name"
                />
                <Button
                  type="button"
                  variant="secondary"
                  disabled={saving || !sublocationSpace || !normalizeName(sublocationName)}
                  onClick={addSublocation}
                  data-testid="waar-inhuis-sublocation-add"
                >
                  Sublocatie toevoegen
                </Button>
              </div>
              {sublocations.map((item, index) => (
                <div key={`${item.space_name}-${item.name}-${index}`} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span>{item.space_name} → {item.name}</span>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={saving}
                    onClick={() => setSublocations((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    data-testid={`waar-inhuis-sublocation-remove-${index}`}
                  >
                    Verwijderen
                  </Button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </Card>

      <Card>
        <div className="rz-form">
          <div>
            <h2 style={{ marginTop: 0 }}>Direct starten met Uitpakken?</h2>
            <p style={{ marginBottom: 0 }}>
              Na een aankoop kan Inhuis je helpen spullen direct aan hun plek te koppelen.
            </p>
          </div>
          <ChoiceButtons
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
          <ChoiceButtons
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
          <ChoiceButtons
            value={almostOut}
            onChange={setAlmostOut}
            disabled={saving}
            testId="waar-inhuis-almost-out"
          />
        </div>
      </Card>

      <p style={{ marginBottom: 0 }}>
        <strong>Je hoeft je locaties nu niet volledig uit te werken. Verfijnen kan later.</strong>
      </p>

      <Button
        type="button"
        variant="primary"
        disabled={saving || !mainLocations.length}
        onClick={finish}
        data-testid="waar-inhuis-finish"
      >
        {saving ? 'Opslaan…' : 'Waar Inhuis instellen'}
      </Button>

      {localError ? <div className="rz-alert">{localError}</div> : null}
      {error ? <div className="rz-alert">{error}</div> : null}
    </div>
  )
}
