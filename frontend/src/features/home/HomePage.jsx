import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import { readStoredAuthContext, isHouseholdViewerFromContext } from '../../lib/authSession.js'

const tiles = [
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
  { key: 'prognoses', label: 'Prognoses', icon: '📊' },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁' },
  { key: 'voorraad', label: 'Voorraad', icon: '📦' },
  { key: 'kassabonnen', label: 'Uitpakken', icon: '🧾' },
  { key: 'kassa', label: 'Kassa', icon: '🧾' },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳' },
  { key: 'recepten', label: 'Recepten', icon: '🍳' },
  { key: 'bestellen', label: 'Bestellen', icon: '📋' },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️' },
  { key: 'admin', label: 'Admin', icon: '🛠️' },
]

export default function HomePage() {
  const navigate = useNavigate()
  const storedContext = readStoredAuthContext()
  const [householdName, setHouseholdName] = useState(storedContext?.active_household_name || '')
  const [isHouseholdAdmin, setIsHouseholdAdmin] = useState(String(storedContext?.display_role || '').toLowerCase() === 'admin')
  const [isViewer, setIsViewer] = useState(isHouseholdViewerFromContext(storedContext))

  useEffect(() => {
    const token = localStorage.getItem('rezzerv_token')
    if (!token) return
    fetch('/api/household', { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error('Huishouden niet beschikbaar')
        return res.json()
      })
      .then((data) => {
        const name = data?.naam || 'Mijn huishouden'
        setHouseholdName(name)
        setIsHouseholdAdmin(Boolean(data?.is_household_admin))
        setIsViewer(Boolean(data?.is_viewer))
        localStorage.setItem('rezzerv_household_name', name)
      })
      .catch(() => {})
  }, [])

  function openTile(key) {
    if (key === 'bijna-op') navigate('/bijna-op')
    if (key === 'voorraad') navigate('/voorraad')
    if (key === 'kassabonnen') navigate('/kassabonnen')
    if (key === 'kassa') navigate('/kassa')
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
              {tiles.filter((tile) => tile.key !== "admin" || isHouseholdAdmin).map((t) => {
                const clickable = ['bijna-op', 'voorraad', 'kassabonnen', 'kassa', 'instellingen', 'admin'].includes(t.key)
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
