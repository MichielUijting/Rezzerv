import { Navigate } from 'react-router-dom'
import { isHouseholdViewerFromContext, readStoredAuthContext } from '../../lib/authSession'

export default function SettingsGuard({ children, allowViewer = true }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />
  if (!allowViewer && isHouseholdViewerFromContext(context)) {
    return <Navigate to="/instellingen" replace />
  }
  return children
}
