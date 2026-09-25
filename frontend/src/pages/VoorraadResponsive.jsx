import { useEffect, useState } from 'react'
import Voorraad from './Voorraad'
import MobileVoorraad from './MobileVoorraad.jsx'
import {
  AUTH_CONTEXT_CHANGED_EVENT,
  readStoredAuthContext,
} from '../lib/authSession.js'
import {
  fetchHouseholdOnboarding,
  readHouseholdOnboarding,
} from '../features/onboarding/onboardingState.js'
import { useMobileAppViewport } from '../app/mobileViewport.js'
import './voorraadResponsive.css'

export function isInventoryLocationTrackingEnabled(onboarding) {
  const level = String(onboarding?.product_configuration?.location_tracking_level || 'none')
    .trim()
    .toLowerCase()
  return level !== 'none'
}

function readInitialLocationTracking(context) {
  if (context?.context_type !== 'regular') return true
  return isInventoryLocationTrackingEnabled(readHouseholdOnboarding(context))
}

export default function VoorraadResponsive() {
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
    if (cached) setLocationTrackingEnabled(isInventoryLocationTrackingEnabled(cached))
    else setLocationTrackingEnabled(false)

    fetchHouseholdOnboarding(context, { force: true })
      .then((onboarding) => {
        if (!cancelled) setLocationTrackingEnabled(isInventoryLocationTrackingEnabled(onboarding))
      })
      .catch(() => {
        if (!cancelled) setLocationTrackingEnabled(false)
      })

    return () => {
      cancelled = true
    }
  }, [context?.user_id, context?.active_household_id, context?.context_type])

  if (isMobileViewport) {
    return <MobileVoorraad locationTrackingEnabled={locationTrackingEnabled} />
  }

  return (
    <div
      className={`rz-inventory-presentation${locationTrackingEnabled ? '' : ' rz-inventory-presentation--locationless'}`}
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <Voorraad />
    </div>
  )
}
