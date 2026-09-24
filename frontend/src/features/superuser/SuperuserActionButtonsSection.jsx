import { useEffect, useState } from 'react'
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

async function saveActionOrder(keys) {
  const response = await fetchJsonWithAuth('/api/platform/action-buttons/order', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keys }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Volgorde van de Startpagina-acties kon niet worden opgeslagen.')
  return Array.isArray(payload?.items) ? payload.items : []
}

function moveBefore(items, sourceKey, targetKey) {
  if (!sourceKey || !targetKey || sourceKey === targetKey) return items
  const source = items.find((item) => item.key === sourceKey)
  const targetExists = items.some((item) => item.key === targetKey)
  if (!source || !targetExists) return items
  const next = items.filter((item) => item.key !== sourceKey)
  const targetIndex = next.findIndex((item) => item.key === targetKey)
  next.splice(targetIndex, 0, source)
  return next.map((item, sortOrder) => ({ ...item, sort_order: sortOrder }))
}

export default function SuperuserActionButtonsSection() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const [saving, setSaving] = useState(false)
  const [savingOrder, setSavingOrder] = useState(false)
  const [draggedKey, setDraggedKey] = useState('')
  const [dragOverKey, setDragOverKey] = useState('')
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    loadActionButtons()
      .then((nextItems) => { if (active) { setItems(nextItems); setError('') } })
      .catch((requestError) => { if (active) setError(requestError?.message || 'Acties op de Startpagina konden niet worden geladen.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  function propose(item) {
    if (saving || savingOrder) return
    setError('')
    setPending({ key: item.key, label: item.label || item.key, enabled: !Boolean(item.enabled) })
  }

  async function confirm() {
    if (!pending || saving || savingOrder) return
    setSaving(true)
    setError('')
    try {
      const updated = await saveActionButton(pending.key, pending.enabled)
      setItems((current) => current.map((item) => item.key === updated?.key ? { ...item, ...updated } : item))
      setPending(null)
      window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
    } catch (requestError) {
      setError(requestError?.message || 'Actie op de Startpagina kon niet worden gewijzigd.')
    } finally {
      setSaving(false)
    }
  }

  async function dropBefore(targetKey) {
    const sourceKey = draggedKey
    setDragOverKey('')
    setDraggedKey('')
    if (!sourceKey || sourceKey === targetKey || savingOrder || saving) return

    const previous = items
    const next = moveBefore(previous, sourceKey, targetKey)
    if (next === previous) return
    const sourceLabel = previous.find((item) => item.key === sourceKey)?.label || sourceKey
    const targetLabel = previous.find((item) => item.key === targetKey)?.label || targetKey

    setItems(next)
    setSavingOrder(true)
    setError('')
    setAnnouncement(`${sourceLabel} wordt voor ${targetLabel} geplaatst.`)
    try {
      const saved = await saveActionOrder(next.map((item) => item.key))
      setItems(saved)
      setAnnouncement(`${sourceLabel} staat nu voor ${targetLabel}.`)
      window.dispatchEvent(new Event('rezzerv-action-buttons-changed'))
    } catch (requestError) {
      setItems(previous)
      setAnnouncement('De vorige volgorde is hersteld omdat opslaan niet lukte.')
      setError(requestError?.message || 'Volgorde van de Startpagina-acties kon niet worden opgeslagen.')
    } finally {
      setSavingOrder(false)
    }
  }

  return (
    <section aria-label="Actieknoppen" data-testid="superuser-action-buttons">
      <h2 style={{ marginTop: 0, fontSize: 20 }}>Actieknoppen op de Startpagina</h2>
      <p style={{ marginTop: 0 }}>
        Bepaal hier platformbreed welke acties op de Startpagina beschikbaar zijn en in welke volgorde ze staan. De instelling geldt voor alle gebruikers en huishoudens.
      </p>
      <p>
        Sleep een actie, houd hem vast en laat hem vóór een andere actie los. De tussenliggende acties schuiven automatisch op en de nieuwe volgorde wordt direct opgeslagen.
      </p>
      <p>
        Dit wijzigt alleen de beschikbaarheid en volgorde van tegels op de Startpagina. Bestaande rollen, permissies, onboarding en backend-autorisatie blijven ongewijzigd en leidend.
      </p>

      <div role="status" aria-live="polite" data-testid="superuser-action-order-status">
        {savingOrder ? 'Nieuwe volgorde opslaan…' : announcement}
      </div>
      {loading ? <p role="status">Acties op de Startpagina laden…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && items.length === 0 ? <p>Geen acties op de Startpagina geregistreerd.</p> : null}

      {!loading && items.length > 0 ? (
        <div data-testid="superuser-action-order-list" style={{ display: 'grid', gap: 12, marginTop: 20 }}>
          {items.map((item, index) => {
            const isPending = pending?.key === item.key
            const isDragTarget = dragOverKey === item.key && draggedKey && draggedKey !== item.key
            return (
              <div
                key={item.key}
                draggable={!saving && !savingOrder && !isPending}
                data-testid={`superuser-action-order-item-${item.key}`}
                data-sort-order={index}
                aria-grabbed={draggedKey === item.key ? 'true' : 'false'}
                onDragStart={(event) => {
                  if (saving || savingOrder || isPending) { event.preventDefault(); return }
                  setDraggedKey(item.key)
                  setAnnouncement(`${item.label || item.key} opgepakt.`)
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', item.key)
                }}
                onDragEnter={(event) => {
                  event.preventDefault()
                  if (draggedKey && draggedKey !== item.key) setDragOverKey(item.key)
                }}
                onDragOver={(event) => {
                  event.preventDefault()
                  event.dataTransfer.dropEffect = 'move'
                  if (draggedKey && draggedKey !== item.key) setDragOverKey(item.key)
                }}
                onDrop={(event) => { event.preventDefault(); void dropBefore(item.key) }}
                onDragEnd={() => { setDraggedKey(''); setDragOverKey('') }}
                style={{
                  cursor: savingOrder ? 'wait' : 'grab',
                  outline: isDragTarget ? '3px solid var(--color-brand-primary, var(--color-ui-primary))' : 'none',
                  outlineOffset: 2,
                  borderRadius: 12,
                }}
              >
                <Card className="rz-card-home">
                  <div data-testid={`superuser-action-button-${item.key}`}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ minWidth: 0, flex: '1 1 420px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span aria-hidden="true" title="Verslepen" style={{ fontSize: 20, lineHeight: 1 }}>☰</span>
                          <strong>{index + 1}. {item.label || item.key}</strong>
                        </div>
                        <p style={{ margin: '6px 0' }}>{item.description}</p>
                        <div style={{ fontSize: 13, color: '#475467' }}>Sleutel: {item.key}</div>
                        <div style={{ marginTop: 6 }}>Status: <strong>{item.enabled ? 'Beschikbaar' : 'Niet beschikbaar'}</strong></div>
                      </div>
                      <Button type="button" variant={item.enabled ? 'secondary' : 'primary'} disabled={saving || savingOrder || isPending} onClick={() => propose(item)}>
                        {item.enabled ? 'Uitschakelen' : 'Inschakelen'}
                      </Button>
                    </div>

                    {isPending ? (
                      <div data-testid="superuser-action-button-confirmation" style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #d0d5dd' }}>
                        <h4 style={{ margin: '0 0 8px 0' }}>Wijziging bevestigen</h4>
                        <p style={{ margin: '0 0 8px 0' }}>
                          <strong>{pending.label}</strong> wordt op de Startpagina platformbreed <strong>{pending.enabled ? 'beschikbaar' : 'niet beschikbaar'}</strong>.
                        </p>
                        <p style={{ margin: '0 0 12px 0' }}>Deze wijziging geeft geen extra rechten en omzeilt geen bestaande autorisatie.</p>
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                          <Button type="button" disabled={saving} onClick={confirm}>{saving ? 'Opslaan…' : 'Definitief bevestigen'}</Button>
                          <Button type="button" variant="secondary" disabled={saving} onClick={() => setPending(null)}>Annuleren</Button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </Card>
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}
