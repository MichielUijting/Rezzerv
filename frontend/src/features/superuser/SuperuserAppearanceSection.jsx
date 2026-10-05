import { useEffect, useState } from 'react'
import Button from '../../ui/Button.jsx'
import {
  DEFAULT_PRIMARY_COLOR,
  applyPrimaryColorPreference,
  normalizePrimaryColor,
} from '../../ui/primaryColorPreference.js'

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Weergave-instelling kon niet worden opgeslagen.')
  return payload
}

export default function SuperuserAppearanceSection() {
  const [color, setColor] = useState(DEFAULT_PRIMARY_COLOR)
  const [draft, setDraft] = useState(DEFAULT_PRIMARY_COLOR)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    request('/api/platform/primary-color')
      .then((payload) => {
        if (!active) return
        const next = normalizePrimaryColor(payload?.primary_color) || DEFAULT_PRIMARY_COLOR
        setColor(next)
        setDraft(next)
        applyPrimaryColorPreference(next)
      })
      .catch((loadError) => { if (active) setError(loadError?.message || 'Hoofdkleur kon niet worden geladen.') })
    return () => { active = false }
  }, [])

  async function save() {
    const normalized = normalizePrimaryColor(draft)
    if (!normalized) {
      setError(`Vul een geldige hexkleur in, bijvoorbeeld ${DEFAULT_PRIMARY_COLOR}.`)
      return
    }
    setSaving(true); setError('')
    try {
      const payload = await request('/api/superuser/primary-color', {
        method: 'PUT',
        body: JSON.stringify({ primary_color: normalized }),
      })
      const next = normalizePrimaryColor(payload?.primary_color) || normalized
      setColor(next)
      setDraft(next)
      applyPrimaryColorPreference(next)
    } catch (saveError) {
      setError(saveError?.message || 'Hoofdkleur kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    setSaving(true); setError('')
    try {
      const payload = await request('/api/superuser/primary-color', { method: 'DELETE' })
      const next = normalizePrimaryColor(payload?.primary_color) || DEFAULT_PRIMARY_COLOR
      setColor(next)
      setDraft(next)
      applyPrimaryColorPreference(next)
    } catch (saveError) {
      setError(saveError?.message || 'Standaardkleur kon niet worden hersteld.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Weergave" data-testid="superuser-appearance">
      <h2 style={{ marginTop: 0 }}>Platformbrede weergave</h2>
      <p>De Superuser bepaalt de primaire donkergroene kleur voor Inhuis. Deze instelling geldt voor alle gebruikers en apparaten.</p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'end', flexWrap: 'wrap' }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <span className="rz-label">Kleur kiezen</span>
          <input
            type="color"
            value={normalizePrimaryColor(draft) || color}
            onChange={(event) => { setDraft(event.target.value.toUpperCase()); setError('') }}
            aria-label="Primaire Inhuis-kleur kiezen"
            data-testid="superuser-primary-color-picker"
            disabled={saving}
          />
        </label>
        <label style={{ display: 'grid', gap: 6 }}>
          <span className="rz-label">Hexkleur</span>
          <input
            className="rz-input"
            value={draft}
            maxLength={7}
            onChange={(event) => { setDraft(event.target.value.toUpperCase()); setError('') }}
            data-testid="superuser-primary-color-hex"
            disabled={saving}
          />
        </label>
        <Button type="button" onClick={save} disabled={saving}>Toepassen</Button>
        <Button type="button" variant="secondary" onClick={reset} disabled={saving}>Standaard herstellen</Button>
      </div>
      <p data-testid="superuser-primary-color-active">Actief: <strong>{color}</strong></p>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  )
}
