import { Navigate } from 'react-router-dom'
import {
  canCurrentUserPerform,
  readStoredAuthContext,
  setLoginMessage,
} from '../../lib/authSession'

export default function PermissionGuard({ permission, children, message = 'Je hebt geen toegang tot deze functie.' }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />
  if (!canCurrentUserPerform(permission, context)) {
    setLoginMessage(message)
    return <Navigate to="/home" replace />
  }
  return children
}
