import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import {
  fetchAuthContext,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  logoutServerSession,
  readStoredAuthContext,
} from '../../lib/authSession.js'

const tiles = [
  { key: 'meldingen', label: 'Meldingen', icon: '✉️' },
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
  { key: 'inzichten', label: 'Inzichten', icon: '📈' },
  { key: 'prognoses', label: 'Prognoses', icon: '📊' },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁' },
  { key: 'voorraad', label: 'Voorraad', icon: '📦' },
  { key: 'productgroepen', label: 'Productgroepen', icon: '🧩' },
  { key: 'kassabonnen', label: 'Uitpakken', icon: '🧾' },
  { key: 'kassa', label: 'Kassa', icon: '🧾' },
  { key: 'spaartegoeden', label: 'Spaartegoeden', icon: '🪙' },
  { key: 'externe-databases', label: 'Externe databases', icon: '🗄️' },
  { key: 'catalogus', label: 'Catalogus', icon: 'CAT' },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳' },
  { key: 'recepten', label: 'Recepten', icon: '🍳' },
  { key: 'bestellen', label: 'Bestellen', icon: '📋' },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️' },
  { key: 'admin', label: 'Admin', icon: '🛠️' },
  { key: 'superuser', label: 'Superuser', icon: '🛡️' },
]

function visibilityFromContext(context) {
  return {
    canOpenAdmin: isHouseholdAdminFromContext(context),
    canOpenExternalDatabases: isFrontteamMemberFromContext(context),
    isPlatformSuperuser: isPlatformSuperuserFromContext(context),
  }
}

export default function HomePage() {
  const navigate = useNavigate()
  const [context, setContext] = useState(() => readStoredAuthContext())
  const visibility = visibilityFromContext(context)

  useEffect(() => {
    let cancelled = false
    fetchAuthContext()
      .then((nextContext) => {
        if (!cancelled) setContext(nextContext)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function logout() {
    await logoutServerSession()
    navigate('/login', { replace: true })
  }

  if (context?.context_type === 'none') {
    return (
      <div className="rz-screen" data-testid="none-session-home">
        <Header title="Platformbeheerder" />
        <div className="rz-content">
          <div className="rz-content-inner">
            <Card className="rz-card-home">
              <h2>Platformbeheerder</h2>
              <p>Er is geen huishoudcontext actief.</p>
              <Button type="button" variant="secondary" onClick={logout} data-testid="none-session-logout">
                Uitloggen
              </Button>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  function openTile(key) {
    if (key === 'meldingen') navigate('/meldingen')
    if (key === 'bijna-op') navigate('/bijna-op')
    if (key === 'winkelen') navigate('/winkelen')
    if (key === 'inzichten') navigate('/inzichten')
    if (key === 'voorraad') navigate('/voorraad')
    if (key === 'productgroepen') navigate('/productgroepen')
    if (key === 'kassabonnen') navigate('/kassabonnen')
    if (key === 'kassa') navigate('/kassa')
    if (key === 'spaartegoeden') navigate('/spaartegoeden')
    if (key === 'externe-databases') navigate('/externe-databases')
    if (key === 'catalogus') navigate('/catalogus')
    if (key === 'instellingen') navigate('/instellingen')
    if (key === 'admin') navigate('/admin')
    if (key === 'superuser') navigate('/superuser')
  }

  function isVisible(tile) {
    if (tile.key === 'meldingen') return !visibility.isPlatformSuperuser
    if (tile.key === 'admin') return visibility.canOpenAdmin
    if (tile.key === 'externe-databases') return visibility.canOpenExternalDatabases
    if (tile.key === 'superuser') return visibility.isPlatformSuperuser
    return true
  }

  return (
    <div className="rz-screen">
      <Header title="Startpagina" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <div className="rz-tile-grid" role="navigation" aria-label="Acties">
              {tiles.filter(isVisible).map((t) => {
                const clickable = ['meldingen', 'bijna-op', 'winkelen', 'inzichten', 'voorraad', 'productgroepen', 'kassabonnen', 'kassa', 'spaartegoeden', 'externe-databases', 'instellingen', 'admin', 'catalogus', 'superuser'].includes(t.key)
                return (
                  <div key={t.key} className="rz-tile" onClick={() => clickable && openTile(t.key)} style={{ cursor: clickable ? 'pointer' : 'default' }}>
                    <div className="rz-tile-icon" aria-hidden="true">{t.icon}</div>
                    <div className="rz-tile-label">{t.label}</div>
                  </div>
                )
              })}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
