import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

/**
 * One deliberate automatic batch action for independently proven receipts.
 * Opening, reading and filtering Identificeren never write; the authorized
 * POST is initiated only by a click. The separate review flow still handles
 * ambiguous cases without overwriting existing identities.
 */
export default function Ed2CuratedMatchingBatch({ onConfirmed }) {
  const { showFeedback } = useAppFeedback()
  const [open, setOpen] = useState(false)
  const [targets, setTargets] = useState([])
  const [targetId, setTargetId] = useState('')
  const [plan, setPlan] = useState(null)
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [autoSummary, setAutoSummary] = useState(null)
  const [aliasName, setAliasName] = useState('')
  const [targetName, setTargetName] = useState('')

  async function request(url, options = {}) {
    const response = await fetchJsonWithAuth(url, options)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || 'Matching kan niet worden beoordeeld.')
    return payload
  }

  // Deliberate matching action only: simply entering Identificeren,
  // filtering or reading a proposal must never write central product data.
  // One click still applies every independently proven eligible tuple in a
  // single server-controlled pass; only conflicts need human review.
  async function recognizeAndReview() {
    if (saving || loading) return
    setSaving(true)
    setAutoSummary(null)
    try {
      const summary = await request('/api/catalog/ed2/bonnamen-matchen/auto', {
        method: 'POST',
      })
      if (summary.ok !== true || summary.barcode_written !== false) {
        throw new Error('De automatische herkenning is niet bevestigd.')
      }
      setAutoSummary(summary)
      showFeedback({ variant: 'success', title: 'Bonnamen gematched',
        message: `${summary.linked} artikelen gematched, ${summary.synonyms_created} synoniemrelaties aangemaakt.` })
      if (summary.linked > 0) onConfirmed?.()
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Automatische herkenning niet uitgevoerd',
        message: error.message || 'De artikelen blijven ongewijzigd.' })
    } finally {
      setSaving(false)
    }
    // An unsuccessful or partially successful automatic pass must not hide
    // remaining exceptions. The review GET below never mutates product data.
    await openReview()
  }

  function confirmAlias() {
    if (saving || !aliasName.trim() || !targetName.trim()) return
    showFeedback({
      variant: 'warning',
      title: 'Bonnaamsynoniem voor alle winkels vastleggen?',
      message: `"\${aliasName.trim()}" wordt als dezelfde productnaam beschouwd als "\${targetName.trim()}".`,
      detail: 'De regel geldt voor alle winkels en winkelartikelnummers. Alleen unieke, aantoonbaar bevestigde Catalogusidentiteiten worden gekoppeld. Bestaande conflicterende koppelingen en barcodes blijven behouden.',
      primaryActionLabel: 'Synoniem bevestigen',
      secondaryActionLabel: 'Annuleren',
      testId: 'ed2-bonnaam-alias-confirm',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const response = await request('/api/catalog/ed2/bonnaam-synoniem/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ alias_name: aliasName, target_name: targetName }),
          })
          if (!response.ok || !response.alias?.ok || response.match_result?.barcode_written !== false) {
            throw new Error('De bonnaamrelatie is niet bevestigd.')
          }
          showFeedback({ variant: 'success', title: 'Bonnaamsynoniem opgeslagen',
            message: `De relatie geldt nu centraal. \${response.match_result.linked} bonartikel(en) gematched.` })
          setAliasName('')
          setTargetName('')
          onConfirmed?.()
        } catch (error) {
          showFeedback({ variant: 'error', title: 'Bonnaamsynoniem niet opgeslagen',
            message: error.message || 'De gegevens blijven ongewijzigd.' })
        } finally { setSaving(false) }
        return false
      },
    })
  }

  async function openReview() {
    setOpen(true)
    setLoading(true)
    try {
      const data = await request('/api/catalog/ed2/curated-matching-batch/preview')
      setTargets(data.targets || [])
      setPlan(null)
      setSelected([])
      setTargetId('')
    } catch (error) {
      showFeedback({ variant: 'error', message: error.message })
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!open || !targetId) return undefined
    let cancelled = false
    const controller = new AbortController()
    setLoading(true)
    request('/api/catalog/ed2/curated-matching-batch/preview?target_product_id='
      + encodeURIComponent(targetId), { signal: controller.signal })
      .then((data) => {
        if (!cancelled) {
          setPlan(data)
          setSelected((data.items || []).map((item) => item.receipt_item_id))
        }
      })
      .catch((error) => {
        if (!cancelled && error.name !== 'AbortError') showFeedback({
          variant: 'error', message: error.message,
        })
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; controller.abort() }
  }, [open, targetId])

  async function apply() {
    if (!plan?.fingerprint || selected.length === 0 || saving) return
    showFeedback({
      variant: 'warning',
      title: 'Matching en synoniemen als één geheel bevestigen',
      message: `De ${selected.length} geselecteerde bonartikelen koppelen aan de gekozen courgettefamilie?`,
      detail: 'De exacte winkel-/bonartikelidentiteiten en afzonderlijke varianten worden bevestigd. Er worden geen barcodes verzonnen. Kassabonnen en huishoudvoorraad blijven ongewijzigd.',
      primaryActionLabel: 'Alles bevestigen', secondaryActionLabel: 'Annuleren',
      testId: 'ed2-curated-batch-confirm',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const result = await request('/api/catalog/ed2/curated-matching-batch/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              target_product_id: targetId,
              receipt_item_ids: selected,
              fingerprint: plan.fingerprint,
            }),
          })
          if (!result.ok || result.barcode_written !== false) {
            throw new Error('De identificatie is niet bevestigd.')
          }
          showFeedback({ variant: 'success', title: 'Matches bevestigd',
            message: `${result.linked} artikelen gekoppeld, ${result.synonyms_created} nieuwe synoniemrelaties.` })
          setOpen(false)
          setPlan(null)
          setSelected([])
          onConfirmed?.()
        } catch (error) {
          showFeedback({ variant: 'error', title: 'Matching niet verwerkt',
            message: error.message || 'Er is niets gewijzigd.' })
        } finally { setSaving(false) }
        return false
      },
    })
  }

  return <section aria-label="Gecontroleerde matching van productfamilies"
    className="rz-external-curated-matching">
    {autoSummary?.status === 'anchor_review_required' ? <p role="status">
      Niet alle productfamilies hebben één bewezen anker. Beoordeel onzekere varianten afzonderlijk.
    </p> : null}
    {autoSummary?.status === 'applied' ? <p role="status">
      {autoSummary.linked} bonartikel(en) gematched, waarvan
      {' '}{autoSummary.linked_from_exact_names || 0} via bewezen of bevestigde bonnamen.
      {' '}{autoSummary.synonyms_created} product-synoniemrelatie(s) aangemaakt.
      {' '}{autoSummary.blocked || 0} conflict(en) overgeslagen.
    </p> : null}
    <Button type="button" variant="secondary" disabled={saving || loading}
      onClick={() => open ? setOpen(false) : recognizeAndReview()}>
      {saving ? 'Automatisch herkennen...' : open
        ? 'Matchingvoorstellen sluiten' : 'Bonnamen matchen'}
    </Button>
    <div className="rz-external-receipt-detail" data-testid="ed2-bonnaam-alias-form">
      <h3>Een bonnaamsynoniem vastleggen</h3>
      <p>Bijvoorbeeld: HV Melk betekent hetzelfde als Halfvolle melk.
        Een bevestigde regel geldt voor alle winkels en nummers, zonder bestaande
        productidentiteiten of barcodes te overschrijven.</p>
      <label htmlFor="ed2-bonnaam-alias">Naam op de bon</label>
      <input id="ed2-bonnaam-alias" value={aliasName} maxLength={200} disabled={saving}
        onChange={(event) => setAliasName(event.target.value)}
        placeholder="HV Melk" />
      <label htmlFor="ed2-bonnaam-target">Is hetzelfde als bonnaam</label>
      <input id="ed2-bonnaam-target" value={targetName} maxLength={200} disabled={saving}
        onChange={(event) => setTargetName(event.target.value)}
        placeholder="Halfvolle melk" />
      <Button type="button" variant="secondary" onClick={confirmAlias}
        disabled={saving || !aliasName.trim() || !targetName.trim()}>
        Bonnaamsynoniem vastleggen
      </Button>
    </div>
    {open ? <div className="rz-external-receipt-detail">
      <h3>Twijfelgevallen van geteste productfamilies beoordelen</h3>
      <p>Alleen veilig te beoordelen kandidaten uit de vastgestelde familie.
        Bewaarde barcodes, bestaande koppelingen en andere producten worden niet overschreven.</p>
      <label htmlFor="ed2-curated-anchor">Bestaand, geïdentificeerd Catalogusproduct</label>
      <select id="ed2-curated-anchor" value={targetId} disabled={loading || saving}
        onChange={(event) => { setTargetId(event.target.value); setPlan(null) }}>
        <option value="">Kies de juiste gewone verse courgette</option>
        {targets.map((item) => <option key={item.product_id} value={item.product_id}>
          {item.product_name}{item.barcode ? ` — ${item.barcode}` : ''}
        </option>)}
      </select>
      {targets.length === 0 && !loading ? <p>Er is nog geen bewezen gewone verse courgette in de Catalogus gevonden.</p> : null}
      {loading ? <p>Voorstellen controleren...</p> : null}
      {plan && !loading ? <>
        <p>{plan.items.length} voorgesteld · {plan.blocked.length} afzonderlijk te beoordelen</p>
        {plan.items.map((item) => <label key={item.receipt_item_id}
          style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBlock: 6 }}>
          <input type="checkbox" checked={selected.includes(item.receipt_item_id)}
            disabled={saving} onChange={(event) => setSelected((current) => event.target.checked
              ? [...current, item.receipt_item_id]
              : current.filter((value) => value !== item.receipt_item_id))} />
          {item.retailer.toUpperCase()} — {item.receipt_line_text}
          {item.receipt_article_number ? ` (${item.receipt_article_number})` : ''}
          {' — '}{item.mode_label}
        </label>)}
        {plan.blocked.map((item) => <p key={item.receipt_item_id} role="status">
          Controleren: {item.retailer} — {item.receipt_line_text}: {item.reason}
        </p>)}
        <Button type="button" disabled={!selected.length || saving || selected.length > 50}
          onClick={apply}>{saving ? 'Bevestigen...' : `${selected.length} matches in één keer bevestigen`}</Button>
      </> : null}
    </div> : null}
  </section>
}
