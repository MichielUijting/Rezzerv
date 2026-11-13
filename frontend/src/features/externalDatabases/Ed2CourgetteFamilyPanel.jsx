import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

/**
 * The family match is only a suggestion until an authorized user confirms an
 * exact receipt identity. Never fabricate a barcode or write on page load.
 */
export default function Ed2CourgetteFamilyPanel({ item, onConfirmed }) {
  const [available, setAvailable] = useState([])
  const [chosen, setChosen] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { showFeedback } = useAppFeedback()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setChosen('')
    const controller = new AbortController()
    fetchJsonWithAuth('/api/catalog/ed2/courgette-family/options?receipt_item_id='
      + encodeURIComponent(item.id), { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data.detail || 'Kandidaten niet beschikbaar.')
        if (!cancelled) setAvailable(data.options || [])
      }).catch((error) => {
        if (!cancelled && error.name !== 'AbortError') showFeedback({
          variant: 'error', title: 'Familievoorstellen niet geladen',
          message: String(error.message || 'Onbekende fout'),
        })
      }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; controller.abort() }
  }, [item.id])

  const option = available.find((row) => row.fingerprint === chosen)

  function requestConfirm() {
    if (!option || saving) return
    showFeedback({
      variant: 'warning', title: 'Bonartikel zonder barcode bevestigen',
      message: option.mode === 'same_product'
        ? `${item.receipt_line_text} (${item.retailer}) koppelen aan ${option.product_name}?`
        : `${item.receipt_line_text} als apart Catalogusproduct en synoniem van ${option.product_name} bevestigen?`,
      detail: 'Dit legt uitsluitend de exacte winkel-/bonartikelidentiteit vast. Er wordt geen barcode verzonnen. Bestaande bonnen, huishoudartikelen en voorraad worden niet gewijzigd.',
      primaryActionLabel: 'Bevestigen', secondaryActionLabel: 'Annuleren',
      testId: 'ed2-curated-family-confirm',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const response = await fetchJsonWithAuth('/api/catalog/ed2/courgette-family/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              receipt_item_id: item.id,
              target_product_id: option.product_id,
              match_mode: option.mode,
              fingerprint: option.fingerprint,
            }),
          })
          const data = await response.json().catch(() => ({}))
          if (!response.ok || data.ok !== true || data.barcode_written !== false) {
            throw new Error(data.detail || 'Identificatie niet opgeslagen.')
          }
          showFeedback({ variant: 'success', title: 'Catalogusidentiteit bevestigd',
            message: data.synonym_created
              ? 'De artikelvariant is als synoniem gekoppeld.'
              : 'De winkel-/bonartikelidentiteit is bewaard zonder barcode.' })
          onConfirmed?.()
        } catch (error) {
          showFeedback({ variant: 'error', title: 'Niet gekoppeld',
            message: error.message || 'Koppeling geweigerd; er is niets gewijzigd.' })
        } finally { setSaving(false) }
        return false
      },
    })
  }

  return <section className="rz-external-receipt-detail" aria-label="Courgettefamilie koppelen zonder barcode">
    <h3>Herkennen zonder barcode — verse courgette</h3>
    <p>Dit is een productfamilievoorstel, geen bewezen barcode.
      Bevestig alleen als je zeker weet dat het bonartikel hetzelfde product is
      of als aparte variant uitwisselbaar is.</p>
    {loading ? <p>Kandidaten laden...</p> : available.length
      ? <>
          <label htmlFor="ed2-courgette-candidate">Bestaand Catalogusproduct</label>
          <select id="ed2-courgette-candidate" value={chosen}
            onChange={(event) => setChosen(event.target.value)} disabled={saving}>
            <option value="">Kies het juiste Catalogusproduct</option>
            {available.map((row) => <option key={row.fingerprint} value={row.fingerprint}>
              {row.product_name} — {row.mode_label}
            </option>)}
          </select>
          <Button disabled={!option || saving} onClick={requestConfirm}>
            {saving ? 'Bevestigen...' : option?.mode === 'synonym_variant'
              ? 'Variant als synoniem bevestigen'
              : 'Bonartikel koppelen'}
          </Button>
        </>
      : <p>Geen geschikt, geïdentificeerd Catalogusproduct gevonden.
          Er wordt niets automatisch aangemaakt of gekoppeld.</p>}
  </section>
}
