import { useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

/**
 * All-product exact receipt-name recognition. Only one explicit click starts
 * the privileged POST; entering, reading and filtering Artikelbeheer are GET.
 * Synonym/product-family decisions remain in their separate curated flow.
 */
export default function Ed2ProvenExactNameMatching({ onConfirmed }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const { showFeedback } = useAppFeedback()

  async function recognize() {
    if (busy) return
    setBusy(true)
    setResult(null)
    try {
      const response = await fetchJsonWithAuth('/api/catalog/ed2/proven-exact-names/auto', {
        method: 'POST',
      })
      const summary = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(summary.detail || 'Exacte bonnamen konden niet worden herkend.')
      }
      if (summary.ok !== true || summary.barcode_written !== false ||
          summary.synonyms_created !== 0) {
        throw new Error('De automatische herkenning is niet bevestigd.')
      }
      setResult(summary)
      showFeedback({
        variant: 'success',
        title: 'Bewezen bonnamen gecontroleerd',
        message: summary.linked > 0
          ? `${summary.linked} bonartikel(en) zonder winkelartikelnummer gekoppeld aan bestaande Catalogusproducten.`
          : 'Geen nieuwe veilige matches gevonden; bestaande gegevens blijven behouden.',
      })
      if (summary.linked > 0) onConfirmed?.()
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Bonnamen niet verwerkt',
        message: error.message || 'Er zijn geen Catalogusgegevens gewijzigd.' })
    } finally {
      setBusy(false)
    }
  }

  return <section aria-label="Algemene bewezen bonnaamherkenning"
    className="rz-external-curated-matching"
    data-testid="ed2-proven-exact-name-matching">
    <Button type="button" variant="secondary" disabled={busy} onClick={recognize}>
      {busy ? 'Bewezen bonnamen herkennen...' : 'Bewezen bonnamen herkennen'}
    </Button>
    {result ? <p role="status">
      {result.linked} artikel(en) aan een bestaand Catalogusproduct gekoppeld.
      {' '}{result.blocked || 0} conflict(en) vragen controle.
      {result.limit_reached ? ' Er zijn nog kandidaten voor een volgende batch.' : ''}
    </p> : null}
  </section>
