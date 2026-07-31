import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { fetchJsonWithAuth, getStoredToken, setLoginMessage } from '../../lib/authSession'

export default function PlatformGuard({ permissionKey, children }) {
  const token = getStoredToken()
  const [status, setStatus] = useState(() => (token ? 'checking' : 'invalid'))

  useEffect(() => {
    if (!token) {
      setStatus('invalid')
      return
    }
    if (!permissionKey) {
      setStatus('forbidden')
      return
    }

    let active = true
    setStatus('checking')
    fetchJsonWithAuth(`/api/platform/toegang?bevoegdheid=${encodeURIComponent(permissionKey)}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!active) return
        if (response.ok && data?.toegang === true) {
          setStatus('ready')
          return
        }
        if (response.status === 403) {
          setStatus('forbidden')
          return
        }
        throw new Error(data?.detail || 'Centrale bevoegdheden konden niet worden gecontroleerd.')
      })
      .catch((error) => {
        if (!active) return
        if (error?.status === 401) {
          setStatus('invalid')
          return
        }
        setLoginMessage(error?.message || 'Centrale bevoegdheden konden niet worden gecontroleerd.')
        setStatus('forbidden')
      })

    return () => { active = false }
  }, [permissionKey, token])

  useEffect(() => {
    if (status === 'forbidden') {
      setLoginMessage('Je hebt geen centrale bevoegdheid voor deze functie.')
    }
  }, [status])

  if (!token || status === 'invalid') return <Navigate to="/login" replace />
  if (status === 'forbidden') return <Navigate to="/home" replace />
  if (status !== 'ready') {
    return <div className="rz-screen"><div className="rz-content"><div className="rz-content-inner">Centrale bevoegdheden controleren…</div></div></div>
  }

  return children
}
