import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { clearAuthSession, fetchAuthContext, getStoredToken, isTokenAlreadyValidated, readStoredAuthContext } from '../../lib/authSession'

export default function SettingsGuard({ children, allowViewer = true }) {
  const token = getStoredToken()
  const cachedContext = readStoredAuthContext()
  const [status, setStatus] = useState(() => {
    if (!token) return 'invalid'
    if (isTokenAlreadyValidated(token) && cachedContext) {
      return 'ready'
    }
    return 'checking'
  })

  useEffect(() => {
    if (!token) {
      setStatus('invalid')
      return
    }
    if (isTokenAlreadyValidated(token) && readStoredAuthContext()) {
      setStatus('ready')
      return
    }
    let active = true
    setStatus('checking')
    fetchAuthContext()
      .then((context) => {
        if (!active) return
        setStatus('ready')
      })
      .catch((error) => {
        if (!active) return
        clearAuthSession(error?.message || 'Je sessie is verlopen. Log opnieuw in.')
        setStatus('invalid')
      })
    return () => { active = false }
  }, [token])


  if (!token || status === 'invalid') return <Navigate to="/login" replace />
  if (status !== 'ready') return <div className="rz-screen"><div className="rz-content"><div className="rz-content-inner">Bevoegdheden controleren…</div></div></div>
  const context = readStoredAuthContext()
  const isViewer = String(context?.display_role || '').trim().toLowerCase() === 'viewer'
  if (!allowViewer && isViewer) return <Navigate to="/instellingen" replace />
  return children
}
