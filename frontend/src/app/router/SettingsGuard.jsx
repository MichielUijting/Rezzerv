import { Navigate } from 'react-router-dom'
import { isHouseholdViewerFromContext, readStoredAuthContext } from '../../lib/authSession'

export default function SettingsGuard({ children, allowViewer = true, allowedContexts = ['regular'] }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />

  const contextType = String(context.context_type || '').trim().toLowerCase()
  if (!allowedContexts.includes(contextType)) {
    return <Navigate to="/home" replace />
  }

  if (!allowViewer && isHouseholdViewerFromContext(context)) {
    return <Navigate to="/instellingen" replace />
  }
  return children
}