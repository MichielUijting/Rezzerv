import { useState } from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { readStoredAuthContext } from '../../lib/authSession.js'
import { selectPrimaryUseCase } from './onboardingState.js'

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

export default function OnboardingPage({ onUseCaseSelected }) {
  const [savingKey, setSavingKey] = useState('')
  const [error, setError] = useState('')

  async function choose(primaryUseCase) {
    setError('')
    setSavingKey(primaryUseCase)
    try {
      const context = readStoredAuthContext()
      await selectPrimaryUseCase(context, primaryUseCase)
      onUseCaseSelected?.()
    } catch (err) {
      setError(err?.message || 'Gebruiksdoel opslaan mislukt.')
    } finally {
      setSavingKey('')
    }
  }

  return (
    <div className="rz-screen" data-testid="onboarding-use-case-page">
      <Header title="Welkom bij Inhuis" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div className="rz-form">
              <div>
                <h1 style={{ marginTop: 0 }}>Waar wil je Inhuis mee beginnen?</h1>
                <p>
                  Kies wat je nu het meest helpt. Daarmee bepaalt Inhuis welke vervolgstappen voor jou relevant zijn.
                </p>
              </div>

              {OPTIONS.map((option) => (
                <Card key={option.key}>
                  <div className="rz-form">
                    <div>
                      <h2 style={{ marginTop: 0, marginBottom: 6 }}>{option.title}</h2>
                      <strong>{option.question}</strong>
                      <p style={{ marginBottom: 0 }}>{option.description}</p>
                    </div>
                    <Button
                      type="button"
                      variant="primary"
                      disabled={Boolean(savingKey)}
                      onClick={() => choose(option.key)}
                      data-testid={`onboarding-choice-${option.key}`}
                    >
                      {savingKey === option.key ? 'Opslaan…' : `Start met ${option.title}`}
                    </Button>
                  </div>
                </Card>
              ))}

              <p style={{ marginBottom: 0 }}>
                <strong>Je kunt later altijd andere mogelijkheden toevoegen.</strong>
              </p>

              {error ? <div className="rz-alert">{error}</div> : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
