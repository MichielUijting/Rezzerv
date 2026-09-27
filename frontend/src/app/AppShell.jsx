import { useLocation } from 'react-router-dom'
import Header from '../ui/Header.jsx'
import Button from '../ui/Button.jsx'

export default function AppShell({ title, children, showExit = true }) {
  const location = useLocation()
  const isSettings = location.pathname === '/instellingen' || location.pathname.startsWith('/instellingen/')

  return (
    <div className={`rz-screen${isSettings ? ' rz-settings-shell' : ''}`} data-settings-shell={isSettings || undefined}>
      <Header title={title} />
      <div className="rz-content">
        <div className="rz-content-inner">
          {children}
        </div>
      </div>

      {showExit && (
        <div className="rz-exitbar">
          <Button variant="secondary" onClick={() => window.close()}>
            Afsluiten
          </Button>
        </div>
      )}
    </div>
  )
}
