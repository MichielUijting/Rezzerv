import { useMemo, useState } from 'react'
import {
  clearAuthSession,
  readStoredAuthContext,
  storeAuthContext,
} from '../../lib/authSession'

export function useAuth() {
  const [session, setSessionState] = useState(() => readStoredAuthContext())

  const isLoggedIn = useMemo(() => Boolean(session?.user_id), [session])

  function setSession(context) {
    setSessionState(storeAuthContext(context))
  }

  function clearSession() {
    clearAuthSession()
    setSessionState(null)
  }

  return { session, isLoggedIn, setSession, clearSession }
}
