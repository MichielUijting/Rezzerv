import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { clearAuthSession, fetchAuthContext, readStoredAuthContext } from '../../lib/authSession'

export default function AuthGuard({ children }) {
  const location = useLocation()
  const [status, setStatus] = useState(() => readStoredAuthContext() ? 'ready' : 'checking')

  useEffect(() => {
    if (readStoredAuthContext()) {
      setStatus('ready')
      return
    }
    let active = true
    setStatus('checking')
    fetchAuthContext()
      .then(() => {
        if (active) setStatus('ready')
      })
      .catch((error) => {
        if (!active) return
        clearAuthSession(error?.message || 'Je sessie is verlopen. Log opnieuw in.')
        setStatus('invalid')
      })
    return () => { active = false }
  }, [])

  if (status === 'invalid') return <Navigate to="/login" replace />
  if (status !== 'ready') return <div className="rz-screen"><div className="rz-content"><div className="rz-content-inner">Sessie controleren…</div></div></div>
  if (readStoredAuthContext()?.context_type === 'none' && location.pathname !== '/home') {
    return <Navigate to="/home" replace />
  }
  return children
}
