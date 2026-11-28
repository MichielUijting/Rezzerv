import { useCallback, useEffect, useState } from 'react'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  fetchConsumableReviewCandidates,
  saveConsumableReviewChoice,
} from './services/householdAutomationService'

const PAGE_SIZE = 10

export default function ConsumableReviewPanel({ enabled }) {
  const { showFeedback } = useAppFeedback()
  const [offset, setOffset] = useState(0)
  const [result, setResult] = useState({ total: 0, items: [] })
  const [isLoading, setIsLoading] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (nextOffset) => {
    setIsLoading(true)
    try {
      const data = await fetchConsumableReviewCandidates({
        offset: nextOffset,
        limit: PAGE_SIZE,
      })
      setResult(data)
      setOffset(nextOffset)
    } catch (error) {
      showFeedback({
        variant: 'error',
        message: error?.message || 'Classificaties laden is niet gelukt.',
      })
    } finally {
      setIsLoading(false)
    }
  }, [showFeedback])

  useEffect(() => {
    if (enabled) load(0)
  }, [enabled, load])

  if (!enabled) return null

  async function choose(row, consumable) {
    if (busy) return
    setBusy(true)
    try {
      const expectedState = row.consumable === null
        ? 'unknown' : row.consumable ? 'true' : 'false'
      await saveConsumableReviewChoice(row.id, consumable, expectedState)
      showFeedback({
        variant: 'success',
        message: 'De keuze voor dit huishoudartikel is vastgelegd.',
      })
      const nextOffset = result.items.length === 1 && offset > 0
        ? Math.max(0, offset - PAGE_SIZE) : offset
      await load(nextOffset)
    } catch (error) {
      showFeedback({
        variant: 'error',
        message: error?.message || 'De keuze is niet opgeslagen.',
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <div style={{ display: 'grid', gap: '12px' }} data-testid="consumable-review-panel">
        <div>
          <h2 style={{ margin: '0 0 8px', fontSize: '20px' }}>
            Verbruiksartikelen beoordelen
          </h2>
          <p style={{ margin: 0, color: '#667085' }}>
            Bij oudere artikelen is niet altijd bekend of de opgeslagen classificatie
            door Inhuis of door een gebruiker is gekozen. Controleer deze artikelen
            en leg jouw keuze vast. Kassabonnen en voorraad blijven hierbij behouden.
          </p>
        </div>
        <p style={{ margin: 0 }}>
          <strong>{result.total}</strong> artikelen met nog onbekende herkomst
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '8px' }}>Artikel</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Opgeslagen</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Actie</th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((row) => (
                <tr key={row.id}>
                  <td style={{ padding: '8px' }}>
                    {row.naam}
                    {row.food_hint ? (
                      <div style={{ fontSize: '12px', color: '#667085' }}>
                        Mogelijk voedsel volgens de catalogus; controle blijft nodig
                      </div>
                    ) : null}
                  </td>
                  <td style={{ padding: '8px' }}>
                    {row.consumable === null ? 'Onbekend' : row.consumable ? 'Ja' : 'Nee'}
                  </td>
                  <td style={{ padding: '8px' }}>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      <Button disabled={isLoading || busy}
                        onClick={() => choose(row, true)}>
                        Verbruiksartikel
                      </Button>
                      <Button variant="secondary" disabled={isLoading || busy}
                        onClick={() => choose(row, false)}>
                        Geen verbruiksartikel
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {!isLoading && result.items.length === 0 ? (
                <tr><td colSpan={3} style={{ padding: '8px' }}>
                  Geen artikelen op deze pagina die beoordeeld moeten worden.
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', flexWrap: 'wrap', gap: '8px',
        }}>
          <span>{result.total
            ? String(offset + 1) + '–' + String(offset + result.items.length)
              + ' van ' + String(result.total)
            : '0 artikelen'}</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <Button variant="secondary" disabled={busy || isLoading || offset === 0}
              onClick={() => load(Math.max(0, offset - PAGE_SIZE))}>
              Vorige
            </Button>
            <Button variant="secondary"
              disabled={busy || isLoading || offset + PAGE_SIZE >= result.total}
              onClick={() => load(offset + PAGE_SIZE)}>
              Volgende
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
