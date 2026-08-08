import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import {
  fetchAuthContext,
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
} from '../../lib/authSession.js'

export default function SuperuserGuard({ children }) {
  const [context, setContext] = useState(() => readStoredAuthContext())
  const [loading, setLoading] = useState(() => !readStoredAuthContext())

  useEffect(() => {
    let cancelled = false
    fetchAuthContext({ force: true })
      .then((nextContext) => {
        if (!cancelled) setContext(nextContext)
      })
      .catch(() => {
        if (!cancelled) setContext(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  if (loading) return null
  if (!isPlatformSuperuserFromContext(context)) {
    return <Navigate to="/home" replace />
  }
  return children
}
