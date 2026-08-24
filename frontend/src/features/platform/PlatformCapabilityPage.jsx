import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import PlatformDiagnosticsPage from './PlatformDiagnosticsPage.jsx'

export default function PlatformCapabilityPage({ item }) {
  const navigate = useNavigate()

  if (item?.key === 'diagnostics') {
    return <PlatformDiagnosticsPage />
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
