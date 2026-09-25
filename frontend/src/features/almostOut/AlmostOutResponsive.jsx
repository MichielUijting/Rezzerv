import { useEffect, useState } from 'react'
import AlmostOutPage from './AlmostOutPage.jsx'
import MobileAlmostOut from './MobileAlmostOut.jsx'
import {
  AUTH_CONTEXT_CHANGED_EVENT,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import {
  fetchHouseholdOnboarding,
  readHouseholdOnboarding,
} from '../onboarding/onboardingState.js'
import { useMobileAppViewport } from '../../app/mobileViewport.js'

export function isAlmostOutLocationTrackingEnabled(onboarding) {
  const level = String(onboarding?.product_configuration?.location_tracking_level || 'none')
    .trim()
    .toLowerCase()
  return level !== 'none'
}

function readInitialLocationTracking(context) {
  if (context?.context_type !== 'regular') return true
  return isAlmostOutLocationTrackingEnabled(readHouseholdOnboarding(context))
}

export default function AlmostOutResponsive() {
  const [context, setContext] = useState(() => readStoredAuthContext())
  const isMobileViewport = useMobileAppViewport()
  const [locationTrackingEnabled, setLocationTrackingEnabled] = useState(() => {
    const initialContext = readStoredAuthContext()
    return readInitialLocationTracking(initialContext)
  })

  useEffect(() => {
    const handleContextChange = () => setContext(readStoredAuthContext())
    window.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
    return () => window.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
  }, [])

  useEffect(() => {
    let cancelled = false

    if (context?.context_type !== 'regular') {
      setLocationTrackingEnabled(true)
      return undefined
    }

    const cached = readHouseholdOnboarding(context)
    if (cached) setLocationTrackingEnabled(isAlmostOutLocationTrackingEnabled(cached))
    else setLocationTrackingEnabled(false)

    fetchHouseholdOnboarding(context, { force: true })
      .then((onboarding) => {
        if (!cancelled) setLocationTrackingEnabled(isAlmostOutLocationTrackingEnabled(onboarding))
      })
      .catch(() => {
        if (!cancelled) setLocationTrackingEnabled(false)
      })

    return () => {
      cancelled = true
    }
  }, [context?.user_id, context?.active_household_id, context?.context_type])

  if (isMobileViewport) {
    return <MobileAlmostOut locationTrackingEnabled={locationTrackingEnabled} />
  }

  return <AlmostOutPage />
}
