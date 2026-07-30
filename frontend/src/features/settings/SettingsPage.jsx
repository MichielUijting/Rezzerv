import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import AuthorizedControl from '../../ui/AuthorizedControl'

export default function SettingsPage() {
  function getTileStyle(disabled = false) {
    return {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px',
      border: `1px solid ${disabled ? '#0f5b32' : '#dfe4ea'}`, borderRadius: '12px',
      color: disabled ? '#0f5b32' : 'inherit', textDecoration: 'none',
      background: disabled ? '#d8f3dc' : '#ffffff', cursor: disabled ? 'not-allowed' : 'pointer',
      boxShadow: disabled ? 'none' : undefined, opacity: 1, width: '100%', boxSizing: 'border-box',
    }
  }

  function ProtectedTile({ permission, to, title, description, testId }) {
    return (
      <AuthorizedControl permission={permission} className="rz-authorized-control--tile">
        <Link to={to} style={getTileStyle(false)} data-testid={testId}>
          <div><div style={{ fontWeight: 600 }}>{title}</div><div style={{ color: '#667085', fontSize: '14px' }}>{description}</div></div>
          <div aria-hidden="true">→</div>
        </Link>
      </AuthorizedControl>
    )
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '18px' }} data-testid="settings-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Instellingen</h2>
            <p style={{ margin: 0, color: '#667085' }}>Beheer hier voorkeuren voor de weergave en automatisering binnen Rezzerv.</p>
          </div>
          <Link to="/instellingen/artikeldetails/veldzichtbaarheid" style={getTileStyle(false)}>
            <div><div style={{ fontWeight: 600 }}>Artikeldetails</div><div style={{ color: '#667085', fontSize: '14px' }}>Veldzichtbaarheid</div></div><div aria-hidden="true">→</div>
          </Link>
          <ProtectedTile permission="article_groups.manage" to="/instellingen/artikelgroepen" title="Artikelgroepen" description="Beheer je eigen indeling van voorraadartikelen" />
          <Link to="/instellingen/privacy-datadeling" style={getTileStyle(false)}>
            <div><div style={{ fontWeight: 600 }}>Privacy &amp; Datadeling</div><div style={{ color: '#667085', fontSize: '14px' }}>Persoonlijke toestemming per gebruiker · standaard alles uit</div></div><div aria-hidden="true">→</div>
          </Link>
          <ProtectedTile permission="locations.manage" to="/instellingen/locaties" title="Locaties" description="Beheer locaties en sublocaties voor Voorraad, Kassa en Incidentele aankoop" />
          <ProtectedTile permission="catalog.manage" to="/instellingen/winkelimport" title="Winkelimport" description="Vereenvoudigingsniveau voor het huishouden" />
          <ProtectedTile permission="household_settings.manage" to="/instellingen/huishouden" title="Huishouden" description="Naam, leden en rollen beheren" />
          <Link to="/instellingen/huishouden/autorisaties" style={getTileStyle(false)} data-testid="authorization-settings-link">
            <div><div style={{ fontWeight: 600 }}>Autorisaties</div><div style={{ color: '#667085', fontSize: '14px' }}>Bekijk welke mogelijkheden bij elke rol horen</div></div><div aria-hidden="true">→</div>
          </Link>
          <ProtectedTile permission="household_settings.manage" to="/instellingen/huishoudautomatisering" title="Huishoudautomatisering" description="Slim afboeken bij herhaalaankoop" />
          <ProtectedTile permission="almost_out.update" to="/instellingen/bijna-op-voorspelling" title="Bijna op voorspelling" description="Huishoudbrede bijna-op voorspelling en regelprioriteit" />
        </div>
      </Card>
    </AppShell>
  )
}
