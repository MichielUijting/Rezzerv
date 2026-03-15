import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'

const tiles = [
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
  { key: 'prognoses', label: 'Prognoses', icon: '📊' },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁' },
  { key: 'voorraad', label: 'Voorraad', icon: '📦' },
  { key: 'winkels', label: 'Winkels', icon: '🏬' },
  { key: 'kassabon', label: 'Kassabon', icon: '🧾' },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳' },
  { key: 'recepten', label: 'Recepten', icon: '🍳' },
  { key: 'bestellen', label: 'Bestellen', icon: '📋' },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️' },
  { key: 'admin', label: 'Admin', icon: '🛠️' },
]

export default function HomePage() {
  const navigate = useNavigate()
  const [householdName, setHouseholdName] = useState('')

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
        localStorage.setItem('rezzerv_household_name', name)
      })
      .catch(() => {})
  }, [])

  function openTile(key) {
    if (key === 'voorraad') navigate('/voorraad')
    if (key === 'winkels') navigate('/winkels')
    if (key === 'kassabon') navigate('/kassabon')
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
              {tiles.map((t) => {
                const clickable = ['voorraad', 'winkels', 'kassabon', 'instellingen', 'admin'].includes(t.key)
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
