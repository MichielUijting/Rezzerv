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
import {
  MOBILE_INVENTORY_MEDIA_QUERY,
  isMobileInventoryEligibleContext,
  isMobileInventoryViewport,
} from './mobileInventoryAccess.js'
import './voorraadResponsive.css'

function readViewportMatch() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_INVENTORY_MEDIA_QUERY).matches
}

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
  const [isMobileViewport, setIsMobileViewport] = useState(readViewportMatch)
  const [locationTrackingEnabled, setLocationTrackingEnabled] = useState(() => {
    const initialContext = readStoredAuthContext()
    return readInitialLocationTracking(initialContext)
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mediaQuery = window.matchMedia(MOBILE_INVENTORY_MEDIA_QUERY)
    const handleViewportChange = () => setIsMobileViewport(isMobileInventoryViewport(mediaQuery))
    const handleContextChange = () => setContext(readStoredAuthContext())

    handleViewportChange()
    window.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
    mediaQuery.addEventListener?.('change', handleViewportChange)

    return () => {
      window.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
      mediaQuery.removeEventListener?.('change', handleViewportChange)
    }
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

  if (isMobileViewport && isMobileInventoryEligibleContext(context)) {
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
