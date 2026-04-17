import { readStoredAuthContext, isHouseholdAdminFromContext, isHouseholdViewerFromContext } from '../../lib/authSession'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'

export default function SettingsPage() {
  const authContext = readStoredAuthContext()
  const isViewer = isHouseholdViewerFromContext(authContext)
  const isAdmin = isHouseholdAdminFromContext(authContext)

  function getTileStyle(disabled = false) {
    return {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '14px 16px',
      border: `1px solid ${disabled ? '#0f5b32' : '#dfe4ea'}`,
      borderRadius: '12px',
      color: disabled ? '#0f5b32' : 'inherit',
      textDecoration: 'none',
      background: disabled ? '#d8f3dc' : '#ffffff',
      cursor: disabled ? 'not-allowed' : 'pointer',
      boxShadow: disabled ? 'none' : undefined,
      opacity: 1,
    }
  }

  function handleDisabledClick(event) {
    event.preventDefault()
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
            <div>
              <div style={{ fontWeight: 600 }}>Artikeldetails</div>
              <div style={{ color: '#667085', fontSize: '14px' }}>Veldzichtbaarheid</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
          <Link to="/instellingen/privacy-datadeling" style={getTileStyle(false)}>
            <div>
              <div style={{ fontWeight: 600 }}>Privacy &amp; Datadeling</div>
              <div style={{ color: '#667085', fontSize: '14px' }}>Persoonlijke toestemming per gebruiker · standaard alles uit</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>

          <Link to="/instellingen/locaties" style={getTileStyle(!isAdmin)} aria-disabled={isAdmin ? 'false' : 'true'} onClick={!isAdmin ? handleDisabledClick : undefined}>
            <div>
              <div style={{ fontWeight: 600 }}>Locaties</div>
              <div style={{ color: !isAdmin ? '#0f5b32' : '#667085', fontSize: '14px' }}>{!isAdmin ? 'Alleen Admin kan dit scherm openen.' : 'Beheer locaties en sublocaties voor Voorraad, Kassa en Incidentele aankoop'}</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>


          <Link to="/instellingen/winkelimport" style={getTileStyle(isViewer)} aria-disabled={isViewer ? 'true' : 'false'} onClick={isViewer ? handleDisabledClick : undefined}>
            <div>
              <div style={{ fontWeight: 600 }}>Winkelimport</div>
              <div style={{ color: isViewer ? '#0f5b32' : '#667085', fontSize: '14px' }}>{isViewer ? 'Zichtbaar voor kijkers, maar alleen Artikeldetails is beschikbaar.' : 'Vereenvoudigingsniveau voor het huishouden · alleen beheerder kan wijzigen'}</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
          <Link to="/instellingen/huishouden" style={getTileStyle(isViewer)} aria-disabled={isViewer ? 'true' : 'false'} onClick={isViewer ? handleDisabledClick : undefined}>
            <div>
              <div style={{ fontWeight: 600 }}>Huishouden</div>
              <div style={{ color: isViewer ? '#0f5b32' : '#667085', fontSize: '14px' }}>{isViewer ? 'Zichtbaar voor kijkers, maar alleen Artikeldetails is beschikbaar.' : 'Leden, rollen en kijkrechten beheren'}</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
          <Link to="/instellingen/huishoudautomatisering" style={getTileStyle(isViewer)} aria-disabled={isViewer ? 'true' : 'false'} onClick={isViewer ? handleDisabledClick : undefined}>
            <div>
              <div style={{ fontWeight: 600 }}>Huishoudautomatisering</div>
              <div style={{ color: isViewer ? '#0f5b32' : '#667085', fontSize: '14px' }}>{isViewer ? 'Zichtbaar voor kijkers, maar alleen Artikeldetails is beschikbaar.' : 'Slim afboeken bij herhaalaankoop · alleen beheerder kan wijzigen'}</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
          <Link to="/instellingen/bijna-op-voorspelling" style={getTileStyle(isViewer)} aria-disabled={isViewer ? 'true' : 'false'} onClick={isViewer ? handleDisabledClick : undefined}>
            <div>
              <div style={{ fontWeight: 600 }}>Bijna op voorspelling</div>
              <div style={{ color: isViewer ? '#0f5b32' : '#667085', fontSize: '14px' }}>{isViewer ? 'Zichtbaar voor kijkers, maar alleen Artikeldetails is beschikbaar.' : 'Huishoudbrede almost-out voorspelling en regelprioriteit'}</div>
            </div>
            <div aria-hidden="true">→</div>
          </Link>
        </div>
      </Card>
    </AppShell>
  )
}
