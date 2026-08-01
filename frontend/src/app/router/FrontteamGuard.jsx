import { Navigate } from 'react-router-dom'
import {
  isFrontteamMemberFromContext,
  readStoredAuthContext,
  setLoginMessage,
} from '../../lib/authSession'

export default function FrontteamGuard({ children }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />
  if (!isFrontteamMemberFromContext(context)) {
    setLoginMessage('Alleen leden van het frontteam hebben toegang tot Externe databases.')
    return <Navigate to="/home" replace />
  }
  return children
}
