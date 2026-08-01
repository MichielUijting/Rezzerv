import { Navigate } from 'react-router-dom'
import { isHouseholdAdminFromContext, readStoredAuthContext, setLoginMessage } from '../../lib/authSession'

export default function AdminGuard({ children }) {
  const context = readStoredAuthContext()
  if (!context) return <Navigate to="/login" replace />
  if (!isHouseholdAdminFromContext(context)) {
    setLoginMessage('Alleen de beheerder van het huishouden heeft toegang tot beheerfuncties.')
    return <Navigate to="/home" replace />
  }
  return children
}
