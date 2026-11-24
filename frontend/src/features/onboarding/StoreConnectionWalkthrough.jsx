import Button from '../../ui/Button.jsx'

const INSTRUCTIONS = [
  {
    title: 'Kies de winkels die je gebruikt',
    description: 'Je hoeft geen winkel te koppelen om Inhuis te gebruiken. Kies in Mijn winkelkoppelingen een winkel en volg de uitleg.',
    next: 'Volgende: aankopen',
  },
  {
    title: 'Laat Inhuis je aankopen controleren',
    description: 'Na een geslaagde AH-koppeling kun je Nu synchroniseren gebruiken. Inhuis controleert welke digitale bonnen beschikbaar zijn; als er geen bonnen zijn, is 0 een normaal resultaat.',
    next: 'Volgende: Inhuis gebruiken',
  },
  {
    title: 'Ontdek het dashboard en de actiebalk',
    description: 'Het dashboard geeft overzicht zodra Inhuis gegevens heeft. Onderaan je telefoon staan snelkoppelingen; via Meer vind je andere functies en Instellingen. Je krijgt zo meteen een korte rondleiding.',
    next: 'Bekijk dashboard met uitleg',
  },
]

/**
 * Guidance is advisory: it never blocks registration, enables an import,
 * marks an AH connection, or guesses the number of retailer receipts.
 */
export default function StoreConnectionWalkthrough({
  step = 0, onStepChange, onFinish, ahConnected = false, disabled = false,
}) {
  const index = Math.min(Math.max(Number(step) || 0, 0), INSTRUCTIONS.length - 1)
  const current = INSTRUCTIONS[index]
  return (
    <section data-testid="onboarding-store-walkthrough" aria-labelledby="onboarding-guide-title"
      style={{ display: 'grid', gap: '12px', minWidth: 0 }}>
      <h2 id="onboarding-guide-title" style={{ margin: 0 }}>Zo start je met Inhuis</h2>
      <p style={{ margin: 0 }}>We helpen je in drie korte stappen. Je kunt altijd een winkel overslaan of later koppelen.</p>
      <p style={{ margin: 0, fontWeight: 700 }} data-testid="onboarding-guide-progress">
        Stap {index + 1} van 3
      </p>
      <h3 style={{ margin: 0 }}>{current.title}</h3>
      <p style={{ margin: 0 }}>{current.description}</p>
      {index === 0 ? (
        <p style={{ margin: 0 }}>
          <strong>Albert Heijn:</strong> meld je aan bij Mijn AH en keer terug naar Inhuis.
          <strong> Lidl en Jumbo:</strong> deze werken met een browserfavoriet; dit is op sommige
          Android-browsers niet beschikbaar. Gebruik die koppelingen eventueel later op een computer.
        </p>
      ) : null}
      {index === 0 && ahConnected ? (
        <p style={{ margin: 0 }} role="status" data-testid="onboarding-guide-ah-connected">
          Albert Heijn is gekoppeld. Je kunt doorgaan naar de volgende stap.
        </p>
      ) : null}
      {index === 1 ? (
        <p style={{ margin: 0 }}>
          In <strong>Historische aankopen</strong> zie je wat Inhuis daadwerkelijk heeft opgeslagen,
          wat nog in verwerking is en wat aandacht nodig heeft. Een opgeslagen bon is niet automatisch
          zichtbaar in de gewone Kassa-lijst. Zonder bruikbare aankoopgegevens zijn voorraad en
          voorspellingen nog niet volledig opgebouwd.
        </p>
      ) : null}
      {index === 2 ? (
        <p style={{ margin: 0 }}>
          <strong>Voorraad</strong> toont wat je hebt, <strong>Kassa</strong> verwerkt bonnen,
          <strong>Boodschappen</strong> helpt bij het winkelen en <strong>Bijna op</strong> geeft
          aanvulsuggesties als er voldoende gegevens zijn. Uitpakken verschijnt wanneer het is
          ingeschakeld. De onderste knoppen kunnen per gebruiker veranderen.
        </p>
      ) : null}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
        {index > 0 ? (
          <Button type="button" variant="secondary" onClick={() => onStepChange?.(index - 1)}
            disabled={disabled} data-testid="onboarding-guide-back">Vorige</Button>
        ) : null}
        <Button type="button" variant="primary"
          onClick={() => index === 2 ? onFinish?.() : onStepChange?.(index + 1)}
          disabled={disabled} data-testid="onboarding-guide-next">
          {current.next}
        </Button>
        <Button type="button" variant="secondary" onClick={() => onFinish?.()}
          disabled={disabled} data-testid="onboarding-guide-skip">
          Winkels later koppelen
        </Button>
      </div>
    </section>
  )
}
