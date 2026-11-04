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
    setLoginMessage('Alleen de superuser en leden van het frontteam hebben toegang tot Artikelbeheer.')
    return <Navigate to="/home" replace />
  }
  return children
}
