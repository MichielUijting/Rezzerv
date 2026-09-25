import { useEffect, useState } from 'react'

export const MOBILE_APP_MEDIA_QUERY = '(max-width: 720px)'

export function isMobileAppViewport(mediaQueryList) {
  return Boolean(mediaQueryList?.matches)
}

export function readMobileAppViewport() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_APP_MEDIA_QUERY).matches
}

export function useMobileAppViewport() {
  const [isMobileViewport, setIsMobileViewport] = useState(readMobileAppViewport)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined

    const mediaQuery = window.matchMedia(MOBILE_APP_MEDIA_QUERY)
    const handleViewportChange = () => setIsMobileViewport(isMobileAppViewport(mediaQuery))

    handleViewportChange()
    mediaQuery.addEventListener?.('change', handleViewportChange)

    return () => {
      mediaQuery.removeEventListener?.('change', handleViewportChange)
    }
  }, [])

  return isMobileViewport
}
