import { useCallback, useEffect, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

async function leesAntwoord(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Actie mislukt')
  return data
}

export default function FrontteamUsersPage() {
  const [gebruikers, setGebruikers] = useState([])
  const [bezig, setBezig] = useState(true)
  const [melding, setMelding] = useState('')

  const laden = useCallback(async () => {
    setBezig(true)
    setMelding('')
    try {
      const response = await fetchJsonWithAuth('/api/platform/gebruikers', { headers: { Accept: 'application/json' } })
      const data = await leesAntwoord(response)
      setGebruikers(data?.items || [])
    } catch (error) {
      setMelding(error.message)
    } finally {
      setBezig(false)
    }
  }, [])

  useEffect(() => { laden() }, [laden])

  async function wijzigFrontteam(gebruiker, frontteam) {
    setMelding('')
    try {
      const response = await fetchJsonWithAuth(`/api/platform/gebruikers/${encodeURIComponent(gebruiker)}/frontteam`, {
        method: 'PUT',
        body: JSON.stringify({ frontteam }),
      })
      await leesAntwoord(response)
      setGebruikers((items) => items.map((item) => item.gebruiker === gebruiker ? { ...item, frontteam } : item))
      setMelding(`${gebruiker} is ${frontteam ? 'toegevoegd aan' : 'verwijderd uit'} Frontteam.`)
    } catch (error) {
      setMelding(error.message)
    }
  }

  return (
    <AppShell title="Supergebruiker / Rezzerv-gebruikers" showExit={false}>
      <Card>
        <div className="rz-support-toolbar">
          <div>
            <h2>Rezzerv-gebruikers</h2>
            <p>Alleen het aanvullende lidmaatschap van Frontteam kan hier worden gewijzigd.</p>
          </div>
          <Button variant="secondary" onClick={laden} disabled={bezig}>Verversen</Button>
        </div>

        {bezig ? <p>Gebruikers laden…</p> : null}
        {!bezig && !gebruikers.length ? <p>Geen gebruikers gevonden.</p> : null}

        <div className="rz-authorization-matrix-wrap">
          <table className="rz-authorization-matrix" data-testid="frontteam-gebruikers-tabel">
            <thead>
              <tr>
                <th>Gebruiker</th>
                <th>Huishouden(s)</th>
                <th>Huishoudrol(len)</th>
                <th>Supergebruiker</th>
                <th>Frontteam</th>
              </tr>
            </thead>
            <tbody>
              {gebruikers.map((item) => (
                <tr key={item.gebruiker}>
                  <td>{item.gebruiker}</td>
                  <td>{(item.huishoudens || []).join(', ') || '—'}</td>
                  <td>{(item.huishoudrollen || []).join(', ') || '—'}</td>
                  <td>{item.supergebruiker ? 'Ja' : 'Nee'}</td>
                  <td>
                    <input
                      type="checkbox"
                      checked={Boolean(item.frontteam)}
                      disabled={Boolean(item.supergebruiker)}
                      onChange={(event) => wijzigFrontteam(item.gebruiker, event.target.checked)}
                      aria-label={`Frontteam voor ${item.gebruiker}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {melding ? <p className="rz-support-feedback" role="status">{melding}</p> : null}
      </Card>
    </AppShell>
  )
}
