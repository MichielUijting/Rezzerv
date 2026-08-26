import { useState } from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { fetchAuthContext, readStoredAuthContext } from '../../lib/authSession.js'
import InhuisHalenOnboardingPage from './InhuisHalenOnboardingPage.jsx'
import WatInhuisOnboardingPage from './WatInhuisOnboardingPage.jsx'
import WaarInhuisOnboardingPage from './WaarInhuisOnboardingPage.jsx'
import SharedHouseholdMinimumPage from './SharedHouseholdMinimumPage.jsx'
import { ChoiceSummary, RadioChoices } from './OnboardingChoiceControls.jsx'
import {
  completeInhuisHalenOnboarding,
  completeSharedHouseholdMinimum,
  completeWatInhuisOnboarding,
  completeWaarInhuisOnboarding,
  isInhuisHalenFollowUp,
  isSharedHouseholdMinimum,
  isWatInhuisFollowUp,
  isWaarInhuisFollowUp,
  readHouseholdOnboarding,
  selectPrimaryUseCase,
} from './onboardingState.js'

const OPTIONS = [
  {
    key: 'inhuis_halen',
    title: 'Inhuis halen',
    question: 'Ik wil weten wat ik nodig heb.',
    description: 'Help mij bepalen wat aangevuld moet worden en boodschappen doen.',
  },
  {
    key: 'wat_inhuis',
    title: 'Wat Inhuis',
    question: 'Ik wil overzicht van wat ik heb.',
    description: 'Geef mij een eenvoudig overzicht van mijn spullen of voorraad.',
  },
  {
    key: 'waar_inhuis',
    title: 'Waar Inhuis',
    question: 'Ik wil weten waar alles ligt.',
    description: 'Help mij spullen en voorraad op de juiste plek terug te vinden.',
  },
]

function optionTitle(key) {
  return OPTIONS.find((option) => option.key === key)?.title || ''
}

function onOff(value, onLabel = 'Ja', offLabel = 'Nee') {
  return value ? onLabel : offLabel
}

function persistedProfileChoices(onboarding) {
  const config = onboarding?.product_configuration
  if (!config) return []

  if (onboarding?.primary_use_case === 'inhuis_halen') {
    return [
      { label: 'Eenvoudige voorraad', value: onOff(config.simple_inventory_enabled) },
      { label: 'Bijna-op meldingen', value: onOff(config.almost_out_notifications_enabled) },
      { label: 'Kassabonnen', value: onOff(config.receipt_processing_enabled, 'Nu', 'Later') },
      { label: 'Gerechten', value: onOff(config.recipes_enabled, 'Nu', 'Later') },
    ]
  }

  if (onboarding?.primary_use_case === 'wat_inhuis') {
    return [
      { label: 'Voorraad bijhouden', value: config.inventory_tracking_level === 'quantity' ? 'Ook aantallen' : 'Alleen aanwezigheid' },
      { label: 'Globale plekken', value: config.location_tracking_level === 'global' ? 'Ja' : 'Nee' },
      { label: 'Bijna op', value: onOff(config.almost_out_enabled) },
      { label: 'Winkelen', value: onOff(config.shopping_enabled, 'Nu', 'Later') },
    ]
  }

  if (onboarding?.primary_use_case === 'waar_inhuis') {
    return [
      { label: 'Locaties', value: config.location_tracking_level === 'exact' ? 'Exacte plekken' : 'Geen exacte plekken' },
      { label: 'Uitpakken', value: onOff(config.unpacking_enabled, 'Nu', 'Later') },
      { label: 'Kassabonnen', value: onOff(config.receipt_processing_enabled, 'Nu', 'Later') },
      { label: 'Bijna op', value: onOff(config.almost_out_enabled) },
    ]
  }

  return []
}

export default function OnboardingPage({ onUseCaseSelected }) {
  const context = readStoredAuthContext()
  const initialOnboarding = readHouseholdOnboarding(context)
  const [onboarding, setOnboarding] = useState(() => initialOnboarding)
  const [selectedPrimaryUseCase, setSelectedPrimaryUseCase] = useState(
    () => String(initialOnboarding?.primary_use_case || ''),
  )
  const [savingKey, setSavingKey] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [error, setError] = useState('')

  async function choose(primaryUseCase = selectedPrimaryUseCase) {
    if (!primaryUseCase) return
    setError('')
    setSavingKey(primaryUseCase)
    try {
      const updated = await selectPrimaryUseCase(context, primaryUseCase)
      setOnboarding(updated)
      setSelectedPrimaryUseCase(primaryUseCase)
    } catch (err) {
      setError(err?.message || 'Gebruiksdoel opslaan mislukt.')
    } finally {
      setSavingKey('')
    }
  }

  async function completeInhuisHalen(preferences) {
    setError('')
    setSavingProfile(true)
    try {
      const updated = await completeInhuisHalenOnboarding(context, preferences)
      setOnboarding(updated)
    } catch (err) {
      setError(err?.message || 'Inhuis halen instellen mislukt.')
    } finally {
      setSavingProfile(false)
    }
  }

  async function completeWatInhuis(preferences) {
    setError('')
    setSavingProfile(true)
    try {
      const updated = await completeWatInhuisOnboarding(context, preferences)
      setOnboarding(updated)
    } catch (err) {
      setError(err?.message || 'Wat Inhuis instellen mislukt.')
    } finally {
      setSavingProfile(false)
    }
  }

  async function completeWaarInhuis(preferences) {
    setError('')
    setSavingProfile(true)
    try {
      const updated = await completeWaarInhuisOnboarding(context, preferences)
      setOnboarding(updated)
    } catch (err) {
      setError(err?.message || 'Waar Inhuis instellen mislukt.')
    } finally {
      setSavingProfile(false)
    }
  }

  async function completeSharedMinimum(preferences) {
    setError('')
    setSavingProfile(true)
    try {
      const updated = await completeSharedHouseholdMinimum(context, preferences)
      setOnboarding(updated)
      await fetchAuthContext({ force: true })
      onUseCaseSelected?.()
    } catch (err) {
      setError(err?.message || 'Huishouden afronden mislukt.')
    } finally {
      setSavingProfile(false)
    }
  }

  const showInhuisHalenFollowUp = isInhuisHalenFollowUp(onboarding)
  const showWatInhuisFollowUp = isWatInhuisFollowUp(onboarding)
  const showWaarInhuisFollowUp = isWaarInhuisFollowUp(onboarding)
  const showSharedHouseholdMinimum = isSharedHouseholdMinimum(onboarding)
  const primaryUseCaseTitle = optionTitle(onboarding?.primary_use_case || selectedPrimaryUseCase)

  return (
    <div className="rz-screen" data-testid="onboarding-use-case-page">
      <Header title={primaryUseCaseTitle ? `Welkom bij Inhuis · ${primaryUseCaseTitle}` : 'Welkom bij Inhuis'} />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            {showInhuisHalenFollowUp ? (
              <InhuisHalenOnboardingPage
                onSubmit={completeInhuisHalen}
                saving={savingProfile}
                error={error}
              />
            ) : showWatInhuisFollowUp ? (
              <WatInhuisOnboardingPage
                onSubmit={completeWatInhuis}
                saving={savingProfile}
                error={error}
              />
            ) : showWaarInhuisFollowUp ? (
              <WaarInhuisOnboardingPage
                onSubmit={completeWaarInhuis}
                saving={savingProfile}
                error={error}
              />
            ) : showSharedHouseholdMinimum ? (
              <SharedHouseholdMinimumPage
                initialHouseholdName={onboarding?.household_name || ''}
                primaryUseCaseTitle={primaryUseCaseTitle}
                previousChoices={persistedProfileChoices(onboarding)}
                onSubmit={completeSharedMinimum}
                saving={savingProfile}
                error={error}
              />
            ) : (
              <div className="rz-form">
                <div>
                  <h1 style={{ marginTop: 0 }}>Waar wil je Inhuis mee beginnen?</h1>
                  <p>
                    Kies wat je nu het meest helpt. De keuze wordt pas opgeslagen als je op Verder drukt.
                  </p>
                </div>

                <ChoiceSummary
                  items={[
                    { label: 'Start met', value: optionTitle(selectedPrimaryUseCase) || 'Nog niet gekozen' },
                  ]}
                />

                <RadioChoices
                  name="Waar wil je Inhuis mee beginnen"
                  value={selectedPrimaryUseCase}
                  onChange={setSelectedPrimaryUseCase}
                  disabled={Boolean(savingKey)}
                  testId="onboarding-choice"
                  options={OPTIONS.map((option) => ({
                    value: option.key,
                    label: option.title,
                    description: `${option.question} ${option.description}`,
                    testId: `onboarding-choice-${option.key}`,
                  }))}
                />

                <Button
                  type="button"
                  variant="primary"
                  disabled={!selectedPrimaryUseCase || Boolean(savingKey)}
                  onClick={() => choose()}
                  data-testid="onboarding-primary-continue"
                >
                  {savingKey ? 'Opslaan…' : 'Verder'}
                </Button>

                <p style={{ marginBottom: 0 }}>
                  <strong>Je kunt vóór Verder altijd een andere radioknop kiezen.</strong>
                </p>

                {error ? <div className="rz-alert">{error}</div> : null}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
