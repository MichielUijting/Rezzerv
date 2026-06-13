import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button'

export default function ExternalDatabasesPage() {
  const navigate = useNavigate()

  return (
    <div className="rz-screen">
      <Header title="Externe databases" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card>
            <div style={{ display: 'grid', gap: '16px' }}>
              <div style={{ color: '#2e7d4d', fontSize: 18 }}>
                Externe databases
              </div>
              <div style={{ color: '#2e7d4d' }}>
                Voorbereiding voor koppelingen met externe productdatabases zoals Open Food Facts.
              </div>
              <div style={{ color: '#5f7a68' }}>
                In een volgende stap wordt hier de GTIN-zoekfunctie en automatische productkoppeling toegevoegd.
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button variant="secondary" type="button" onClick={() => navigate('/home')}>
                  Terug
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}