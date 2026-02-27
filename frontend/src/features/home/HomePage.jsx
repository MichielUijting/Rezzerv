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
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' }
]

export default function HomePage() {
  return (
    <div className="rz-screen">
      <Header title="Startpagina" />

      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div className="rz-tile-grid" role="navigation" aria-label="Acties">
              {tiles.map(t => (
                <div key={t.key} className="rz-tile">
                  <div className="rz-tile-icon" aria-hidden="true">{t.icon}</div>
                  <div className="rz-tile-label">{t.label}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="rz-buildtag" aria-hidden="true">Rezzerv v01.04.02</div>
    </div>
  )
}
