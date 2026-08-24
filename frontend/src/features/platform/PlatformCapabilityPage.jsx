import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import PlatformAuditPage from './PlatformAuditPage.jsx'
import PlatformAuthorizationsPage from './PlatformAuthorizationsPage.jsx'
import PlatformBackgroundJobsPage from './PlatformBackgroundJobsPage.jsx'
import PlatformDiagnosticsPage from './PlatformDiagnosticsPage.jsx'
import PlatformFeatureFlagsPage from './PlatformFeatureFlagsPage.jsx'
import PlatformIntegrationsPage from './PlatformIntegrationsPage.jsx'
import PlatformRecoveryPage from './PlatformRecoveryPage.jsx'
import PlatformSessionsPage from './PlatformSessionsPage.jsx'
import PlatformTechnicalConfigurationPage from './PlatformTechnicalConfigurationPage.jsx'
import PlatformTestFixturesPage from './PlatformTestFixturesPage.jsx'
import PlatformUsersPage from './PlatformUsersPage.jsx'

export default function PlatformCapabilityPage({ item }) {
  const navigate = useNavigate()

  if (item?.key === 'diagnostics') {
    return <PlatformDiagnosticsPage />
  }

  if (item?.key === 'audit') {
    return <PlatformAuditPage />
  }

  if (item?.key === 'integrations') {
    return <PlatformIntegrationsPage />
  }

  if (item?.key === 'background-jobs') {
    return <PlatformBackgroundJobsPage />
  }

  if (item?.key === 'recovery') {
    return <PlatformRecoveryPage />
  }

  if (item?.key === 'technical-configuration') {
    return <PlatformTechnicalConfigurationPage />
  }

  if (item?.key === 'test-fixtures') {
    return <PlatformTestFixturesPage />
  }

  if (item?.key === 'feature-flags') {
    return <PlatformFeatureFlagsPage />
  }

  if (item?.key === 'sessions') {
    return <PlatformSessionsPage />
  }

  if (item?.key === 'users') {
    return <PlatformUsersPage />
  }

  if (item?.key === 'permissions') {
    return <PlatformAuthorizationsPage />
  }

  return (
    <div className="rz-screen" data-testid={`platform-capability-${item.key}`}>
      <Header title={item.label} />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>{item.label}</h2>
            <p>{item.description}</p>
            <p>Je bent voor dit platformonderdeel geautoriseerd.</p>
            <p>De functionele beheeracties voor dit onderdeel worden afzonderlijk aangesloten.</p>
            <Button type="button" variant="secondary" onClick={() => navigate('/home')}>
              Terug naar platformbeheer
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
