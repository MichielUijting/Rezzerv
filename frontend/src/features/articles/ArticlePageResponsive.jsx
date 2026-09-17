import { useEffect, useState } from 'react'
import ArticlePage from './ArticlePage.jsx'
import MobileArticlePage from './MobileArticlePage.jsx'
import {
  AUTH_CONTEXT_CHANGED_EVENT,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import {
  MOBILE_INVENTORY_MEDIA_QUERY,
  isMobileInventoryEligibleContext,
  isMobileInventoryViewport,
} from '../../pages/mobileInventoryAccess.js'

function readViewportMatch() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_INVENTORY_MEDIA_QUERY).matches
}

export default function ArticlePageResponsive() {
  const [context, setContext] = useState(() => readStoredAuthContext())
  const [isMobileViewport, setIsMobileViewport] = useState(readViewportMatch)

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

  if (isMobileViewport && isMobileInventoryEligibleContext(context)) {
    return <MobileArticlePage />
  }

  return <ArticlePage />
}
