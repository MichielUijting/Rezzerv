import Button from '../../ui/Button'
import { useNavigate } from 'react-router-dom'

const AREAS = [
  { key: 'identity', title: 'Identificeren' },
  { key: 'classify', title: 'Classificeren' },
  { key: 'synonyms', title: 'Synoniemen' },
  { key: 'sync', title: 'Synchroniseren' },
]

/**
 * Workflow navigation only: independent work queues are not summed.
 * Until identity-safe server-side work items exist, the receipt overview
 * remains strictly a receipt-article view, not a unique product backlog.
 */
export default function ClassificationWorkMonitor({ activeArea, onAreaChange }) {
  const navigate = useNavigate()

  return <section aria-label="Werkgebieden Artikelbeheer" data-testid="classification-work-monitor">
    <div className="rz-article-management-areas" role="group" aria-label="Kies werkgebied">
      {AREAS.map((area) => <Button key={area.key} type="button"
        variant={area.key === activeArea ? 'primary' : 'secondary'}
        aria-pressed={area.key === activeArea}
        onClick={() => onAreaChange(area.key)}>
        {area.title}
      </Button>)}
    </div>
    {activeArea === 'identity' ? <p>
      Identificeer bonartikelen voordat je ze aan de centrale Catalogus koppelt.
      De onderstaande aantallen betreffen bonartikelregistraties, geen unieke Catalogusartikelen.
    </p> : null}
    {activeArea === 'classify' ? <div data-testid="classification-work-area">
      <h3>Classificeren</h3>
      <p>Classificeer centrale Catalogusartikelen volgens GS1 GPC en CBS ECOICOPv2.
        Elke indeling heeft een eigen officiële bron en bevestiging. Dezelfde
        Catalogusidentiteit hoeft niet per bon opnieuw te worden geclassificeerd.</p>
      <div className="rz-article-management-areas">
        <Button type="button" onClick={() => navigate('/catalogus/gpc-classificeren')}>GS1 GPC openen</Button>
        <Button type="button" onClick={() => navigate('/catalogus/artikelclassificaties-toekennen')}>CBS openen</Button>
      </div>
    </div> : null}
    {activeArea === 'synonyms' ? <div data-testid="synonym-work-area">
      <h3>Synoniemen</h3>
      <p>Beoordeel voorgestelde relaties tussen Catalogusartikelen.
        Vergelijkbare namen zijn nog geen bevestigde productidentiteit.</p>
      <Button type="button" onClick={() => navigate('/artikelsynoniemen')}>Artikel-synoniemen openen</Button>
    </div> : null}
    {activeArea === 'sync' ? <div data-testid="synchronization-work-area">
      <h3>Synchroniseren</h3>
      <p>De classificatieovername bij bevestigde synoniemen wordt ontwikkeld in PR #645.
        Openstaande en mislukte synchronisaties krijgen pas een teller wanneer de
        centrale verwerking betrouwbaar en controleerbaar kan worden gemeten.</p>
      <p data-testid="classification-sync-evidence">Er is nog geen gevalideerde synchronisatiewerkvoorraad beschikbaar.
        Er worden daarom geen fictieve aantallen of automatische verwerkingsknoppen getoond.</p>
    </div> : null}
  </section>
}
