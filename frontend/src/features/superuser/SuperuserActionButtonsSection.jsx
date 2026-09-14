import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function loadActionButtons() {
  const response = await fetchJsonWithAuth('/api/platform/action-buttons')
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Acties op de Startpagina konden niet worden geladen.')
  return Array.isArray(payload?.items) ? payload.items : []
}

async function saveActionButton(key, enabled) {
  const response = await fetchJsonWithAuth(`/api/platform/action-buttons/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Actie op de Startpagina kon niet worden gewijzigd.')
  return payload?.item
}

export default function SuperuserActionButtonsSection() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    loadActionButtons()
      .then((nextItems) => { if (active) { setItems(nextItems); setError('') } })
      .catch((requestError) => { if (active) setError(requestError?.message || 'Acties op de Startpagina konden niet worden geladen.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const groupedItems = useMemo(() => {
    const groups = new Map()
    for (const item of items) {
      const group = String(item.group || 'Startpagina')
      if (!groups.has(group)) groups.set(group, [])
      groups.get(group).push(item)
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, 'nl'))
  }, [items])

  function propose(item) {
    if (saving) return
    setError('')
    setPending({ key: item.key, label: item.label || item.key, enabled: !Boolean(item.enabled) })
  }

  async function confirm() {
    if (!pending || saving) return
    setSaving(true)
    setError('')
    try {
      const updated = await saveActionButton(pending.key, pending.enabled)
      setItems((current) => current.map((item) => item.key === updated?.key ? updated : item))
      setPending(null)
      window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
    } catch (requestError) {
      setError(requestError?.message || 'Actie op de Startpagina kon niet worden gewijzigd.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Actieknoppen" data-testid="superuser-action-buttons">
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Actieknoppen op de Startpagina</h2>
      <p style={{ marginTop: 0 }}>
        Bepaal hier platformbreed welke acties op de Startpagina beschikbaar zijn. De instelling geldt voor alle gebruikers en huishoudens.
      </p>
      <p>
        Dit wijzigt alleen de beschikbaarheid van de tegel op de Startpagina. Knoppen binnen Kassa, Voorraad, Winkelen of andere functionaliteiten worden hierdoor niet gewijzigd.
      </p>
      <p>Bestaande rollen, permissies en backend-autorisatie blijven ongewijzigd en leidend. Een wijziging wordt pas opgeslagen na een tweede bevestiging.</p>

      {loading ? <p role="status">Acties op de Startpagina laden…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && items.length === 0 ? <p>Geen acties op de Startpagina geregistreerd.</p> : null}

      {!loading ? groupedItems.map(([group, groupItems]) => (
        <div key={group} style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 17 }}>{group}</h3>
          <div style={{ display: 'grid', gap: 12 }}>
            {groupItems.map((item) => {
              const isPending = pending?.key === item.key
              return (
                <Card key={item.key} className="rz-card-home">
                  <div data-testid={`superuser-action-button-${item.key}`}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ minWidth: 0, flex: '1 1 420px' }}>
                        <strong>{item.label || item.key}</strong>
                        <p style={{ margin: '6px 0' }}>{item.description}</p>
                        <div style={{ fontSize: 13, color: '#475467' }}>Sleutel: {item.key}</div>
                        <div style={{ marginTop: 6 }}>Status: <strong>{item.enabled ? 'Beschikbaar' : 'Niet beschikbaar'}</strong></div>
                      </div>
                      <Button
                        type="button"
                        variant={item.enabled ? 'secondary' : 'primary'}
                        disabled={saving || isPending}
                        onClick={() => propose(item)}
                      >
                        {item.enabled ? 'Uitschakelen' : 'Inschakelen'}
                      </Button>
                    </div>

                    {isPending ? (
                      <div
                        data-testid="superuser-action-button-confirmation"
                        style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #d0d5dd' }}
                      >
                        <h4 style={{ margin: '0 0 8px 0' }}>Wijziging bevestigen</h4>
                        <p style={{ margin: '0 0 8px 0' }}>
                          <strong>{pending.label}</strong> wordt op de Startpagina platformbreed{' '}
                          <strong>{pending.enabled ? 'beschikbaar' : 'niet beschikbaar'}</strong>.
                        </p>
                        <p style={{ margin: '0 0 12px 0' }}>Deze wijziging geeft geen extra rechten en omzeilt geen bestaande autorisatie.</p>
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                          <Button type="button" disabled={saving} onClick={confirm}>
                            {saving ? 'Opslaan…' : 'Definitief bevestigen'}
                          </Button>
                          <Button type="button" variant="secondary" disabled={saving} onClick={() => setPending(null)}>
                            Annuleren
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </Card>
              )
            })}
          </div>
        </div>
      )) : null}
    </section>
  )
}
