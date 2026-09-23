import { useEffect, useState } from 'react'
import { MOBILE_INVENTORY_MEDIA_QUERY } from '../pages/mobileInventoryAccess.js'
import MobileAppBottomNavigation from './MobileAppBottomNavigation.jsx'
import MobileBackButton from './MobileBackButton.jsx'
import './mobileComponents.css'

function readMobileViewport() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_INVENTORY_MEDIA_QUERY).matches
}

export default function MobileNavigationBoundary({ children }) {
  const [isMobileViewport, setIsMobileViewport] = useState(readMobileViewport)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mediaQuery = window.matchMedia(MOBILE_INVENTORY_MEDIA_QUERY)
    const handleChange = () => setIsMobileViewport(Boolean(mediaQuery.matches))
    handleChange()
    mediaQuery.addEventListener?.('change', handleChange)
    return () => mediaQuery.removeEventListener?.('change', handleChange)
  }, [])

  if (!isMobileViewport) return children

  return (
    <div className="rz-mobile-global-navigation-frame" data-testid="mobile-navigation-boundary">
      <div className="rz-mobile-global-back-row">
        <MobileBackButton fallbackRoute="/home" />
      </div>
      {children}
      <MobileAppBottomNavigation />
    </div>
  )
}
