import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import MobileRecentActionsBar from '../ui/MobileRecentActionsBar.jsx'
import { MobileBackControl } from '../ui/MobileModuleHeader.jsx'
import {
  AUTH_CONTEXT_CHANGED_EVENT,
  canCurrentUserPerform,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
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
import './mobileAppChrome.css'

const MORE_NAV_ITEM = { key: 'meer', label: 'Meer', route: '/home', icon: 'menu' }

function mobileNavIconType(key) {
  if (key === 'meldingen') return 'bell'
  if (key === 'voorraad') return 'inventory'
  if (key === 'bijna-op') return 'clock'
  if (key === 'winkelen') return 'cart'
  if (key === 'kassabonnen' || key === 'kassa') return 'receipt'
  return 'menu'
}

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
    const selected = selectRecentActionTiles({
      recentKeys: readRecentActionKeys(context),
      availableTiles: availableActionTiles,
      excludeKeys: activeKey ? [activeKey] : [],
      limit: 4,
    }).map((tile) => ({
      key: tile.key,
      label: tile.label,
      route: ACTION_ROUTE_BY_KEY[tile.key],
      icon: mobileNavIconType(tile.key),
    }))
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
  const [context, setContext] = useState(() => readStoredAuthContext())
  const isMobileViewport = useMobileAppViewport()

  useEffect(() => {
    const handleContextChange = () => setContext(readStoredAuthContext())
    window.addEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
    return () => window.removeEventListener(AUTH_CONTEXT_CHANGED_EVENT, handleContextChange)
  }, [])

  if (!isMobileViewport) return children

  return (
    <div className="rz-mobile-app-chrome" data-testid="mobile-app-chrome">
      {location.pathname !== '/home' ? <MobileBackControl testId="mobile-global-back" /> : null}
      {children}
      <div className="rz-mobile-app-bottom-space" aria-hidden="true" />
      <MobileBottomNavigationRuntime context={context} pathname={location.pathname} />
    </div>
  )
}
