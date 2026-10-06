import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import MobileRecentActionsBar from '../ui/MobileRecentActionsBar.jsx'
import { MobileBackControl } from '../ui/MobileModuleHeader.jsx'
import {
  AUTH_CONTEXT_CHANGED_EVENT,
  canCurrentUserPerform,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
  logoutServerSession,
} from '../lib/authSession.js'
import { readHouseholdOnboarding } from '../features/onboarding/onboardingState.js'
import { buildHomeNavigation } from '../features/home/homeNavigation.js'
import {
  ACTION_ROUTE_BY_KEY,
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from '../features/home/recentActionUsage.js'
import useFeatureAvailability from '../features/platform/useFeatureAvailability.js'
import { useActionButtonAvailability } from '../features/platform/actionButtonAvailability.js'
import { useMobileAppViewport } from './mobileViewport.js'
import { useAppFeedback } from '../ui/AppFeedbackProvider.jsx'
import './mobileAppChrome.css'

const MORE_NAV_ITEM = { key: 'meer', label: 'Meer', route: '/meer', iconType: 'menu', showLabel: true }
const MANDATORY_BOTTOM_NAV_KEY = 'bijna-op'
const MOBILE_ICON_TYPE_BY_KEY = Object.freeze({
  meldingen: 'info',
  voorraad: 'shelf',
  kassa: 'register',
  kassabonnen: 'shopping-bag',
  'bijna-op': 'almost-out',
  winkelen: 'cart',
})

function activeActionKey(pathname = '') {
  const normalizedPath = String(pathname || '')
  return Object.entries(ACTION_ROUTE_BY_KEY)
    .sort((left, right) => right[1].length - left[1].length)
    .find(([, route]) => normalizedPath === route || normalizedPath.startsWith(`${route}/`))?.[0] || ''
}

function MobileBottomNavigationRuntime({ context, pathname }) {
  const features = useFeatureAvailability()
  const actionAvailability = useActionButtonAvailability({
    enabled: Boolean(context && context.context_type !== 'none'),
  })
  const onboarding = readHouseholdOnboarding(context)
  const visibility = {
    canOpenAdmin: isHouseholdAdminFromContext(context),
    canOpenExternalDatabases: isFrontteamMemberFromContext(context),
    isPlatformSuperuser: isPlatformSuperuserFromContext(context),
    canManageLocations: canCurrentUserPerform('locations.manage', context),
  }

  const homeNavigation = buildHomeNavigation({
    onboarding,
    visibility,
    features,
    actionButtons: actionAvailability.items,
    actionOrder: actionAvailability.order,
  })

  const availableActionTiles = useMemo(() => {
    const seen = new Set()
    return [...homeNavigation.primaryTiles, ...homeNavigation.moreTiles]
      .filter((tile) => {
        const route = ACTION_ROUTE_BY_KEY[tile.key]
        if (!tile?.clickable || !route || seen.has(tile.key)) return false
        seen.add(tile.key)
        return true
      })
  }, [homeNavigation])

  const activeKey = activeActionKey(pathname)
  const bottomNavItems = useMemo(() => {
    const mandatoryTile = availableActionTiles.find((tile) => tile.key === MANDATORY_BOTTOM_NAV_KEY) || null
    const excludedKeys = [MANDATORY_BOTTOM_NAV_KEY]
    if (activeKey && activeKey !== MANDATORY_BOTTOM_NAV_KEY) excludedKeys.push(activeKey)

    const recentTiles = selectRecentActionTiles({
      recentKeys: readRecentActionKeys(context),
      availableTiles: availableActionTiles,
      excludeKeys: excludedKeys,
      limit: mandatoryTile ? 3 : 4,
    })

    const uniqueTiles = []
    const seen = new Set()
    for (const tile of [mandatoryTile, ...recentTiles].filter(Boolean)) {
      if (seen.has(tile.key)) continue
      seen.add(tile.key)
      uniqueTiles.push(tile)
    }

    const selected = uniqueTiles.slice(0, 4).map((tile) => {
      const iconType = MOBILE_ICON_TYPE_BY_KEY[tile.key] || null
      return {
        key: tile.key,
        label: tile.label,
        route: ACTION_ROUTE_BY_KEY[tile.key],
        iconType,
        icon: iconType ? null : tile.icon,
        showLabel: false,
      }
    })
    return [...selected, MORE_NAV_ITEM]
  }, [activeKey, availableActionTiles, context?.user_id])

  return (
    <MobileRecentActionsBar
      items={bottomNavItems}
      testId="mobile-global-bottom-nav"
      ariaLabel="Mobiele hoofdnavigatie"
      onAction={(item) => {
        if (item.key !== 'meer') recordRecentAction(item.key, context)
      }}
    />
  )
}

export default function MobileAppChrome({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { showFeedback } = useAppFeedback()
  const [context, setContext] = useState(() => readStoredAuthContext())
  const isMobileViewport = useMobileAppViewport()

  useEffect(() => {
    const handleContextChange = () => setContext(readStoredAuthContext())
    window.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
    return () => window.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
  }, [])

  if (!isMobileViewport) return children

  function handleKassaBack() {
    const event = new Event('inhuis:mobile-kassa-back', { cancelable: true })
    window.dispatchEvent(event)
    if (!event.defaultPrevented) {
      const historyIndex = Number(window.history.state?.idx ?? 0)
      navigate(historyIndex > 0 ? -1 : '/home')
    }
  }

  function handleHomeBack() {
    const event = new Event('inhuis:mobile-home-back', { cancelable: true })
    window.dispatchEvent(event)
    if (event.defaultPrevented) return
    showFeedback({
      variant: 'warning',
      title: 'Inhuis verlaten',
      message: 'Wil je uitloggen?',
      dismissMode: 'action-only',
      primaryActionLabel: 'Uitloggen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        await logoutServerSession()
        navigate('/login', { replace: true })
      },
      key: 'mobile-home-exit-confirmation',
      testId: 'mobile-home-exit-confirmation',
    })
  }

  const isSuperuserRoute = location.pathname === '/superuser' || location.pathname.startsWith('/superuser/')

  return (
    <div className="rz-mobile-app-chrome" data-testid="mobile-app-chrome">
      {isSuperuserRoute ? (
        <header className="rz-mobile-superuser-header" data-testid="mobile-superuser-header">
          <MobileBackControl testId="mobile-global-back" />
          <strong>Superuser</strong>
          <span className="rz-mobile-superuser-header-mark" aria-label="InHuis">InHuis</span>
        </header>
      ) : (
        <MobileBackControl testId="mobile-global-back" onBack={location.pathname === '/home' ? handleHomeBack : location.pathname === '/kassa' || location.pathname === '/kassa/nieuw' ? handleKassaBack : null} />
      )}
      {children}
      <div className="rz-mobile-app-bottom-space" aria-hidden="true" />
      <MobileBottomNavigationRuntime context={context} pathname={location.pathname} />
    </div>
  )
}
