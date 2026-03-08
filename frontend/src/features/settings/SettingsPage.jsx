import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'

export default function SettingsPage() {
  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '18px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Instellingen</h2>
            <p style={{ margin: 0, color: '#667085' }}>Beheer hier persoonlijke voorkeuren voor de weergave van Rezzerv.</p>
          </div>
          <Link to="/instellingen/artikeldetails/veldzichtbaarheid" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', border: '1px solid #dfe4ea', borderRadius: '12px', color: 'inherit', textDecoration: 'none' }}>
            <div>
              <div style={{ fontWeight: 600 }}>Artikeldetails</div>
              <div style={{ color: '#667085', fontSize: '14px' }}>Veldzichtbaarheid</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>

          <Link to="/instellingen/huishoudautomatisering" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', border: '1px solid #dfe4ea', borderRadius: '12px', color: 'inherit', textDecoration: 'none' }}>
            <div>
              <div style={{ fontWeight: 600 }}>Huishoudautomatisering</div>
              <div style={{ color: '#667085', fontSize: '14px' }}>Slim afboeken bij herhaalaankoop</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
        </div>
      </Card>
    </AppShell>
  )
}
