import { useEffect, useState } from 'react'

export const MOBILE_APP_MEDIA_QUERY = '(max-width: 720px)'
export const MOBILE_APP_TOUCH_QUERY = '(pointer: coarse)'
export const MOBILE_APP_LANDSCAPE_MAX_WIDTH = 960

export function isMobileAppViewport(mediaQueryList, touchQueryList, viewportWidth) {
  if (mediaQueryList?.matches) return true

  const width = Number(viewportWidth)
  return Boolean(
    touchQueryList?.matches
      && Number.isFinite(width)
      && width <= MOBILE_APP_LANDSCAPE_MAX_WIDTH,
  )
}

export function readMobileAppViewport() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false

  return isMobileAppViewport(
    window.matchMedia(MOBILE_APP_MEDIA_QUERY),
    window.matchMedia(MOBILE_APP_TOUCH_QUERY),
    window.innerWidth,
  )
}

export function useMobileAppViewport() {
  const [isMobileViewport, setIsMobileViewport] = useState(readMobileAppViewport)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined

    const mediaQuery = window.matchMedia(MOBILE_APP_MEDIA_QUERY)
    const touchQuery = window.matchMedia(MOBILE_APP_TOUCH_QUERY)
    const handleViewportChange = () => setIsMobileViewport(
      isMobileAppViewport(mediaQuery, touchQuery, window.innerWidth),
    )

    handleViewportChange()
    mediaQuery.addEventListener?.('change', handleViewportChange)
    touchQuery.addEventListener?.('change', handleViewportChange)
    window.addEventListener('resize', handleViewportChange)
    window.addEventListener('orientationchange', handleViewportChange)

    return () => {
      mediaQuery.removeEventListener?.('change', handleViewportChange)
      touchQuery.removeEventListener?.('change', handleViewportChange)
      window.removeEventListener('resize', handleViewportChange)
      window.removeEventListener('orientationchange', handleViewportChange)
    }
  }, [])

  return isMobileViewport
}
