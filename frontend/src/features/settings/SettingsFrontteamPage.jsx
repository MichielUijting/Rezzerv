import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import Header from '../../ui/Header.jsx'

const FRONTTEAM_ROLE_KEY = 'platform.frontteam'

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || `Actie mislukt (${response.status})`)
  return payload
}

export default function SettingsFrontteamPage() {
  const [members, setMembers] = React.useState([])
  const [email, setEmail] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [busy, setBusy] = React.useState('')
  const [error, setError] = React.useState('')
  const [result, setResult] = React.useState('')

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const payload = await api('/api/platform/frontteam-management')
      setMembers(Array.isArray(payload?.frontteam_memberships) ? payload.frontteam_memberships : [])
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }, [])

  React.useEffect(() => { load() }, [load])

  async function addMember(event) {
    event.preventDefault()
    const normalized = email.trim()
    if (!normalized) { setError('Vul een e-mailadres in.'); return }
    setBusy('add'); setError(''); setResult('')
    try {
      await api('/api/platform/frontteam-management/members', {
        method: 'POST', body: JSON.stringify({ email: normalized }),
      })
      setEmail('')
      setResult(`${normalized} is toegevoegd aan het Frontteam.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  async function setActive(member, active) {
    setBusy(member.user_id); setError(''); setResult('')
    try {
      await api(`/api/platform/authorizations/users/${encodeURIComponent(member.user_id)}/frontteam/${active ? 'grant' : 'revoke'}`, { method: 'POST' })
      setResult(`${member.email} is ${active ? 'geactiveerd' : 'gedeactiveerd'} als Frontteamlid.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  async function remove(member) {
    if (!window.confirm(`${member.email} uit het Frontteam verwijderen? Het Inhuis-account en eigen huishouden blijven bestaan.`)) return
    setBusy(member.user_id); setError(''); setResult('')
    try {
      await api(`/api/platform/frontteam-management/members/${encodeURIComponent(member.user_id)}`, { method: 'DELETE' })
      setResult(`${member.email} is uit het Frontteam verwijderd. Het Inhuis-account en eigen huishouden zijn behouden.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  return (
    <div data-testid="settings-frontteam-page">
      <Header title="Frontteam beheren" subtitle="Beheer de aanvullende Frontteambevoegdheden van bestaande Inhuis-gebruikers." />
      <div className="rz-content"><div className="rz-content-inner">
        <Card>
          <form onSubmit={addMember} data-testid="frontteam-add-form">
            <label htmlFor="frontteam-email"><strong>E-mailadres</strong></label>
            <div className="rz-frontteam-add-row">
              <input id="frontteam-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="naam@voorbeeld.nl" autoComplete="off" />
              <Button type="submit" disabled={busy === 'add'}>{busy === 'add' ? 'Toevoegen...' : 'Toevoegen aan Frontteam'}</Button>
            </div>
            <p>Alleen een bestaand Inhuis-account kan worden toegevoegd. Het eigen huishouden en de huishoudrol blijven ongewijzigd.</p>
          </form>
        </Card>

        {error ? <Card><p role="alert">{error}</p></Card> : null}
        {result ? <Card><p role="status">{result}</p></Card> : null}

        <Card>
          <h2>Frontteamleden</h2>
          {loading ? <p>Frontteamleden laden...</p> : members.length === 0 ? <p>Er zijn nog geen Frontteamleden.</p> : (
            <div className="rz-frontteam-table-wrap">
              <table className="rz-frontteam-table">
                <thead><tr><th>E-mailadres</th><th>Status</th><th>Acties</th></tr></thead>
                <tbody>
                  {members.map((member) => {
                    const active = (member.platform_role_keys || []).includes(FRONTTEAM_ROLE_KEY) && member.frontteam_status === 'active'
                    const disabled = busy === member.user_id
                    return (
                      <tr key={member.user_id} data-testid={`frontteam-member-${member.user_id}`}>
                        <td>{member.email}</td>
                        <td><strong>{active ? 'Actief' : 'Inactief'}</strong></td>
                        <td>
                          <div className="rz-frontteam-actions">
                            {active
                              ? <Button type="button" variant="secondary" disabled={disabled} onClick={() => setActive(member, false)}>Deactiveren</Button>
                              : <Button type="button" disabled={disabled} onClick={() => setActive(member, true)}>Activeren</Button>}
                            <Button type="button" variant="secondary" disabled={disabled} onClick={() => remove(member)}>Verwijderen</Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div></div>
    </div>
  )
}
