import { useEffect, useState } from 'react'
import Button from '../../ui/Button.jsx'

const TOUR = [
  {
    heading: 'Welkom op je dashboard',
    body: 'Dit is je startpagina. Naarmate je kassabonnen en artikelen in Inhuis verwerkt, groeit je overzicht vanzelf. Een leeg dashboard na registratie is normaal.',
  },
  {
    heading: 'Zo werken de knoppen onderin',
    body: 'Op Android zie je onderaan snelkoppelingen naar beschikbare of recent gebruikte acties. Je kunt bijvoorbeeld Boodschappen, Kassa en Voorraad tegenkomen. De exacte knoppen kunnen veranderen. Via Meer vind je de andere functies en Instellingen.',
  },
  {
    heading: 'Wat kun je nu doen?',
    body: 'Kassa helpt bij het verwerken van bonnen. Voorraad toont wat je in huis hebt. Boodschappen helpt bij het winkelen; Bijna op kan aanvullingen voorstellen zodra er gegevens zijn. Uitpakken is beschikbaar wanneer die functie is ingeschakeld. Winkels kun je later beheren via Instellingen → Winkelkoppelingen.',
  },
]

/** Only shown after the voluntary new-account onboarding completion route. */
export default function FirstUseDashboardGuide({ onClose }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    function keyDown(event) {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', keyDown)
    return () => window.removeEventListener('keydown', keyDown)
  }, [onClose])
  return (
    <div data-testid="first-use-dashboard-guide" role="presentation"
      style={{ position: 'fixed', inset: 0, zIndex: 1500, background: 'rgba(0, 0, 0, .48)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
      <section role="dialog" aria-modal="true" aria-labelledby="first-use-guide-heading"
        style={{ width: '100%', maxWidth: '480px', maxHeight: '90dvh', overflowY: 'auto',
          background: 'var(--color-surface, #fff)', color: 'var(--color-text, #222)',
          borderRadius: '14px', padding: '20px', display: 'grid', gap: '14px',
          boxShadow: '0 8px 30px rgba(0,0,0,.25)' }}>
        <span style={{ fontWeight: 700 }} data-testid="first-use-guide-progress">
          Kennismaking: stap {step + 1} van 3
        </span>
        <h2 id="first-use-guide-heading" style={{ margin: 0 }}>{TOUR[step].heading}</h2>
        <p style={{ margin: 0 }}>{TOUR[step].body}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
          {step > 0 ? (
            <Button type="button" variant="secondary" onClick={() => setStep(step - 1)}
              data-testid="first-use-guide-back">Vorige</Button>
          ) : null}
          <Button type="button" variant="primary" autoFocus
            onClick={() => step === TOUR.length - 1 ? onClose?.() : setStep(step + 1)}
            data-testid="first-use-guide-next">
            {step === TOUR.length - 1 ? 'Ik ga Inhuis gebruiken' : 'Volgende'}
          </Button>
          <Button type="button" variant="secondary" onClick={() => onClose?.()}
            data-testid="first-use-guide-close">Uitleg overslaan</Button>
        </div>
      </section>
    </div>
  )
}
