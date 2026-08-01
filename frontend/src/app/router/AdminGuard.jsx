import { Navigate } from 'react-router-dom'
import {
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
  setLoginMessage,
} from '../../lib/authSession'

export default function AdminGuard({ children }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />
  if (!isPlatformSuperuserFromContext(context)) {
    setLoginMessage('Alleen de platform-supergebruiker heeft toegang tot platformbeheer.')
    return <Navigate to="/home" replace />
  }
  return children
}
