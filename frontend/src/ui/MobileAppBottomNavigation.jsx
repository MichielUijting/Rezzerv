import { useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { readStoredAuthContext, canCurrentUserPerform, isFrontteamMemberFromContext, isHouseholdAdminFromContext, isPlatformSuperuserFromContext } from '../lib/authSession.js'
import { readHouseholdOnboarding } from '../features/onboarding/onboardingState.js'
import { buildHomeNavigation } from '../features/home/homeNavigation.js'
import useFeatureAvailability from '../features/platform/useFeatureAvailability.js'
import { useActionButtonAvailability } from '../features/platform/actionButtonAvailability.js'
import {
  ACTION_ROUTE_BY_KEY,
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from '../features/home/recentActionUsage.js'
import MobileRecentActionsBar from './MobileRecentActionsBar.jsx'

const MORE_NAV_ITEM = { key: 'meer', label: 'Meer', route: '/home', icon: 'menu' }

export function resolveActiveMobileNavKey(pathname = '') {
  const normalized = String(pathname || '').split('?')[0]
  const entries = Object.entries(ACTION_ROUTE_BY_KEY)
    .sort(([, a], [, b]) => b.length - a.length)
  const match = entries.find(([, route]) => normalized === route || normalized.startsWith(`${route}/`))
  return match?.[0] || ''
}

function mobileNavIconType(key) {
  if (key === 'meldingen') return 'bell'
  if (key === 'voorraad') return 'inventory'
  if (key === 'bijna-op') return 'clock'
  if (key === 'winkelen') return 'cart'
  if (key === 'kassabonnen' || key === 'kassa') return 'receipt'
  return 'menu'
}

export default function MobileAppBottomNavigation({
  activeKey = '',
  testId = 'mobile-app-bottom-navigation',
}) {
  const location = useLocation()
  const context = readStoredAuthContext()
  const resolvedActiveKey = activeKey || resolveActiveMobileNavKey(location.pathname)
  const onboarding = readHouseholdOnboarding(context)
  const features = useFeatureAvailability()
  const actionAvailability = useActionButtonAvailability({
    enabled: Boolean(context && context.context_type !== 'none'),
  })

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
  }, [homeNavigation.primaryTiles, homeNavigation.moreTiles])

  const items = useMemo(() => {
    const recent = selectRecentActionTiles({
      recentKeys: readRecentActionKeys(context),
      availableTiles: availableActionTiles,
      excludeKeys: resolvedActiveKey ? [resolvedActiveKey] : [],
      limit: 4,
    }).map((tile) => ({
      key: tile.key,
      label: tile.label,
      route: ACTION_ROUTE_BY_KEY[tile.key],
      icon: mobileNavIconType(tile.key),
    }))
    return [...recent, MORE_NAV_ITEM]
  }, [resolvedActiveKey, availableActionTiles, context?.user_id])

  return (
    <MobileRecentActionsBar
      items={items}
      testId={testId}
      ariaLabel="Hoofdnavigatie"
      onAction={(item) => {
        if (item?.key && item.key !== 'meer') recordRecentAction(item.key, context)
      }}
    />
  )
}
