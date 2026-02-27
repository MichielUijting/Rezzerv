import { useMemo, useState } from 'react'

export function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem('rezzerv_token') || '')

  const isLoggedIn = useMemo(() => Boolean(token), [token])

  function setSession(newToken) {
    localStorage.setItem('rezzerv_token', newToken)
    setToken(newToken)
  }

  function clearSession() {
    localStorage.removeItem('rezzerv_token')
    setToken('')
  }

  return { token, isLoggedIn, setSession, clearSession }
}
