import { useEffect, useRef, useState } from 'react'
import Button from '../../ui/Button.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function readStatus() {
  const response = await fetchJsonWithAuth('/api/platform/login-background')
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Achtergrondinstelling kon niet worden geladen.')
  return payload
}

export default function SuperuserLoginBackgroundSection() {
  const inputRef = useRef(null)
  const [status, setStatus] = useState({ configured: false, revision: null })
  const [selected, setSelected] = useState(null)
  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    readStatus()
      .then((payload) => { if (active) setStatus(payload) })
      .catch((requestError) => { if (active) setError(requestError?.message || 'Achtergrondinstelling kon niet worden geladen.') })
    return () => { active = false }
  }, [])

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  function chooseFile(event) {
    const file = event.target.files?.[0] || null
    setError(''); setMessage('')
    if (!file) return
    const name = String(file.name || '').toLowerCase()
    if (!['image/jpeg', 'image/jpg'].includes(file.type) || !(name.endsWith('.jpg') || name.endsWith('.jpeg'))) {
      setSelected(null); setError('Selecteer een JPG- of JPEG-bestand.'); return
    }
    if (file.size > 8 * 1024 * 1024) {
      setSelected(null); setError('De JPG mag maximaal 8 MB groot zijn.'); return
    }
    if (preview) URL.revokeObjectURL(preview)
    setSelected(file)
    setPreview(URL.createObjectURL(file))
  }

  async function upload() {
    if (!selected || busy) return
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/superuser/login-background', {
        method: 'PUT',
        headers: { 'Content-Type': 'image/jpeg' },
        body: selected,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Achtergrond kon niet worden opgeslagen.')
      setStatus(payload); setSelected(null); setMessage('De nieuwe inlogachtergrond geldt nu voor alle gebruikers.')
      if (inputRef.current) inputRef.current.value = ''
      window.dispatchEvent(new CustomEvent('inhuis-login-background-changed', { detail: payload }))
    } catch (requestError) {
      setError(requestError?.message || 'Achtergrond kon niet worden opgeslagen.')
    } finally { setBusy(false) }
  }

  async function reset() {
    if (busy) return
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/superuser/login-background', { method: 'DELETE' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Standaardachtergrond kon niet worden hersteld.')
      setStatus(payload); setSelected(null); setMessage('De standaardachtergrond is hersteld.')
      if (preview) URL.revokeObjectURL(preview)
      setPreview('')
      if (inputRef.current) inputRef.current.value = ''
      window.dispatchEvent(new CustomEvent('inhuis-login-background-changed', { detail: payload }))
    } catch (requestError) {
      setError(requestError?.message || 'Standaardachtergrond kon niet worden hersteld.')
    } finally { setBusy(false) }
  }

  const currentImage = status.configured && status.revision
    ? `/api/platform/login-background/image?v=${encodeURIComponent(status.revision)}`
    : ''

  return (
    <section aria-label="Achtergrond inlogscherm" data-testid="superuser-login-background">
      <h2 style={{ marginTop: 0 }}>Achtergrond inlogscherm</h2>
      <p>Upload hier een JPG die als achtergrond van het inlogscherm voor alle gebruikers geldt, op desktop én mobiel.</p>
      <p>Maximale bestandsgrootte: 8 MB. Zonder eigen afbeelding gebruikt Inhuis de standaardachtergrond.</p>

      <div className="rz-login-background-preview" data-testid="login-background-preview">
        {preview || currentImage
          ? <img src={preview || currentImage} alt="Voorbeeld achtergrond inlogscherm" style={{ width: '100%', maxWidth: 720, maxHeight: 360, objectFit: 'cover', borderRadius: 'var(--radius-md)' }} />
          : <div style={{ padding: 32, background: '#f4f1e8', borderRadius: 'var(--radius-md)', maxWidth: 720 }}>Standaard Inhuis-achtergrond</div>}
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
        <input ref={inputRef} type="file" accept=".jpg,.jpeg,image/jpeg" onChange={chooseFile} data-testid="login-background-file" />
        <Button type="button" disabled={!selected || busy} onClick={upload}>{busy ? 'Bezig…' : status.configured ? 'JPG vervangen' : 'JPG uploaden'}</Button>
        {status.configured ? <Button type="button" variant="secondary" disabled={busy} onClick={reset}>Standaardachtergrond herstellen</Button> : null}
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
    </section>
  )
}
