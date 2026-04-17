import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { clearAuthSession, fetchAuthContext, getStoredToken, isHouseholdAdminFromContext, isTokenAlreadyValidated, readStoredAuthContext, setLoginMessage } from '../../lib/authSession'

export default function AdminGuard({ children }) {
  const token = getStoredToken()
  const cachedContext = readStoredAuthContext()
  const [status, setStatus] = useState(() => {
    if (!token) return 'invalid'
    if (isTokenAlreadyValidated(token) && cachedContext) {
      return isHouseholdAdminFromContext(cachedContext) ? 'ready' : 'forbidden'
    }
    return 'checking'
  })

  useEffect(() => {
    if (!token) {
      setStatus('invalid')
      return
    }
    if (isTokenAlreadyValidated(token) && readStoredAuthContext()) {
      setStatus(isHouseholdAdminFromContext(readStoredAuthContext()) ? 'ready' : 'forbidden')
      return
    }
    let active = true
    setStatus('checking')
    fetchAuthContext()
      .then((context) => {
        if (!active) return
        setStatus(isHouseholdAdminFromContext(context) ? 'ready' : 'forbidden')
      })
      .catch((error) => {
        if (!active) return
        clearAuthSession(error?.message || 'Je sessie is verlopen. Log opnieuw in.')
        setStatus('invalid')
      })
    return () => { active = false }
  }, [token])

  useEffect(() => {
    if (status === 'forbidden') {
      setLoginMessage('Alleen de beheerder van het huishouden heeft toegang tot beheerfuncties.')
    }
  }, [status])

  if (!token || status === 'invalid') return <Navigate to="/login" replace />
  if (status === 'forbidden') return <Navigate to="/home" replace />
  if (status !== 'ready') return <div className="rz-screen"><div className="rz-content"><div className="rz-content-inner">Bevoegdheden controleren…</div></div></div>
  
  return children
}
