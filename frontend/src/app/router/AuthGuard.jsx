import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { clearAuthSession, fetchAuthContext, readStoredAuthContext } from '../../lib/authSession'
import { fetchHouseholdOnboarding, requiresInitialUseCase } from '../../features/onboarding/onboardingState.js'

export default function AuthGuard({ children }) {
  const location = useLocation()
  const [status, setStatus] = useState('checking')
  const [onboarding, setOnboarding] = useState(null)

  useEffect(() => {
    let active = true

    async function checkSessionAndOnboarding() {
      setStatus('checking')
      try {
        const context = readStoredAuthContext() || await fetchAuthContext()
        let onboardingState = null
        if (context?.context_type === 'regular') {
          onboardingState = await fetchHouseholdOnboarding(context)
        }
        if (!active) return
        setOnboarding(onboardingState)
        setStatus('ready')
      } catch (error) {
        if (!active) return
        clearAuthSession(error?.message || 'Je sessie is verlopen. Log opnieuw in.')
        setStatus('invalid')
      }
    }

    checkSessionAndOnboarding()
    return () => { active = false }
  }, [location.pathname])

  if (status === 'invalid') return <Navigate to="/login" replace />
  if (status !== 'ready') return <div className="rz-screen"><div className="rz-content"><div className="rz-content-inner">Sessie controleren…</div></div></div>

  const context = readStoredAuthContext()
  if (context?.context_type === 'none' && location.pathname !== '/home') {
    return <Navigate to="/home" replace />
  }

  if (context?.context_type === 'regular') {
    const initialChoiceRequired = requiresInitialUseCase(onboarding)
    if (initialChoiceRequired && location.pathname !== '/onboarding') {
      return <Navigate to="/onboarding" replace />
    }
    if (!initialChoiceRequired && location.pathname === '/onboarding') {
      return <Navigate to="/home" replace />
    }
  }

  return children
}
