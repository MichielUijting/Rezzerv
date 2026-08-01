import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import { fetchAuthContext, readStoredAuthContext } from '../../lib/authSession.js'

const tiles = [
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
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
]

function isAdmin(context) {
  return String(context?.display_role || context?.role || '').trim().toLowerCase() === 'admin'
}

export default function HomePage() {
  const navigate = useNavigate()
  const [isHouseholdAdmin, setIsHouseholdAdmin] = useState(() => isAdmin(readStoredAuthContext()))

  useEffect(() => {
    let cancelled = false
    fetchAuthContext()
      .then((context) => {
        if (!cancelled) setIsHouseholdAdmin(isAdmin(context))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  function openTile(key) {
    if (key === 'bijna-op') navigate('/bijna-op')
    if (key === 'voorraad') navigate('/voorraad')
    if (key === 'productgroepen') navigate('/productgroepen')
    if (key === 'kassabonnen') navigate('/kassabonnen')
    if (key === 'kassa') navigate('/kassa')
    if (key === 'spaartegoeden') navigate('/spaartegoeden')
    if (key === 'externe-databases') navigate('/externe-databases')
    if (key === 'catalogus') navigate('/catalogus')
    if (key === 'instellingen') navigate('/instellingen')
    if (key === 'admin') navigate('/admin')
  }

  return (
    <div className="rz-screen">
      <Header title="Startpagina" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <div className="rz-tile-grid" role="navigation" aria-label="Acties">
              {tiles.filter((tile) => !['admin', 'catalogus'].includes(tile.key) || isHouseholdAdmin).map((t) => {
                const clickable = ['bijna-op', 'voorraad', 'productgroepen', 'kassabonnen', 'kassa', 'spaartegoeden', 'externe-databases', 'instellingen', 'admin', 'catalogus'].includes(t.key)
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
