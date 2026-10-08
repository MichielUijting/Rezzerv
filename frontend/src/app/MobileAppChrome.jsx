import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import MobileRecentActionsBar from '../ui/MobileRecentActionsBar.jsx'
import MobileModuleHeader from '../ui/MobileModuleHeader.jsx'
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

const MORE_NAV_ITEM = { key: 'meer', label: 'Meer', route: '', iconType: 'menu', showLabel: true, actionOnly: true }
const MANDATORY_BOTTOM_NAV_KEY = 'bijna-op'
const DEFAULT_FIXED_ACTION_BAR_KEYS = Object.freeze(['winkelen', 'kassa', 'kassabonnen', 'voorraad'])
const MOBILE_ICON_TYPE_BY_KEY = Object.freeze({
  meldingen: 'info',
  voorraad: 'shelf',
  kassa: 'payment-card',
  kassabonnen: 'shopping-bag',
  'bijna-op': 'almost-out',
  winkelen: 'cart',
  instellingen: 'settings',
})

const MOBILE_ROUTE_TITLES = Object.freeze([
  ['/dashboard', 'Inzichten'],
  ['/voorraad/incidentele-aankoop', 'Incidentele aankoop'],
  ['/voorraad/', 'Artikel in Voorraad'],
  ['/voorraad', 'Voorraad'],
  ['/kassabonnen/batch/', 'Kassabon'],
  ['/kassabonnen', 'Uitpakken'],
  ['/kassa', 'Kassa'],
  ['/catalogus/', 'Artikel in Catalogus'],
  ['/catalogus', 'Catalogus'],
  ['/winkelen', 'Boodschappen'],
  ['/bijna-op', 'Bijna op'],
  ['/meldingen', 'Meldingen'],
  ['/instellingen/locaties', 'Locaties'],
  ['/instellingen/', 'Instellingen'],
  ['/instellingen', 'Instellingen'],
  ['/superuser', 'Superuser'],
  ['/platform', 'Platformbeheer'],
  ['/productgroepen', 'Productgroepen'],
  ['/spaartegoeden', 'Spaartegoeden'],
  ['/externe-databases', 'Externe databases'],
  ['/onboarding', 'Instellingen'],
  ['/home', 'Dashboard'],
])

function mobileRouteTitle(pathname = '') {
  const normalized = String(pathname || '')
  const matched = MOBILE_ROUTE_TITLES.find(([prefix]) => (
    normalized === prefix || normalized.startsWith(prefix.endsWith('/') ? prefix : prefix + '/')
  ))
  return matched?.[1] || 'Inhuis'
}

function activeActionKey(pathname = '') {
  const normalizedPath = String(pathname || '')
  return Object.entries(ACTION_ROUTE_BY_KEY)
    .sort((left, right) => right[1].length - left[1].length)
    .find(([, route]) => normalizedPath === route || normalizedPath.startsWith(`${route}/`))?.[0] || ''
}

function MobileBottomNavigationRuntime({ context, pathname }) {
  const navigate = useNavigate()
  const [showMore, setShowMore] = useState(false)
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
    let selectedTiles = []

    if (actionAvailability.actionBarLocked) {
      const byKey = new Map(availableActionTiles.map((tile) => [tile.key, tile]))
      const fixedKeys = actionAvailability.fixedActionBarKeys?.length
        ? actionAvailability.fixedActionBarKeys
        : DEFAULT_FIXED_ACTION_BAR_KEYS
      selectedTiles = fixedKeys.map((key) => byKey.get(key)).filter(Boolean).slice(0, 4)
    } else {
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
      selectedTiles = uniqueTiles.slice(0, 4)
    }

    const selected = selectedTiles.map((tile) => {
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
  }, [
    activeKey,
    actionAvailability.actionBarLocked,
    actionAvailability.fixedActionBarKeys,
    availableActionTiles,
    context?.user_id,
  ])

  const bottomKeys = useMemo(() => new Set(bottomNavItems.filter((item) => item.key !== 'meer').map((item) => item.key)), [bottomNavItems])
  const moreTiles = useMemo(() => {
    const remaining = availableActionTiles.filter((tile) => !bottomKeys.has(tile.key))
    return remaining.length ? remaining : availableActionTiles
  }, [availableActionTiles, bottomKeys])

  function openMoreTile(tile) {
    const route = ACTION_ROUTE_BY_KEY[tile.key]
    if (!route) return
    recordRecentAction(tile.key, context)
    setShowMore(false)
    navigate(route)
  }

  return (
    <>
    <MobileRecentActionsBar
      items={bottomNavItems}
      testId="mobile-global-bottom-nav"
      ariaLabel="Mobiele hoofdnavigatie"
      onAction={(item) => {
        if (item.key === 'meer') {
          setShowMore(true)
          return
        }
        recordRecentAction(item.key, context)
      }}
    />
    {showMore ? (
      <div className="rz-mobile-more-overlay" role="presentation" onClick={() => setShowMore(false)}>
        <section className="rz-mobile-more-dialog" role="dialog" aria-modal="true" aria-labelledby="mobile-more-dialog-title" data-testid="mobile-more-dialog" onClick={(event) => event.stopPropagation()}>
          <div className="rz-mobile-more-dialog-header">
            <strong id="mobile-more-dialog-title">Meer</strong>
            <button type="button" aria-label="Sluit Meer" onClick={() => setShowMore(false)}>×</button>
          </div>
          <div className="rz-mobile-more-dialog-list">
            {moreTiles.map((tile) => (
              <button key={tile.key} type="button" onClick={() => openMoreTile(tile)} data-testid={`mobile-more-dialog-${tile.key}`}>
                {tile.label}
              </button>
            ))}
          </div>
        </section>
      </div>
    ) : null}
    </>
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
  const backHandler = location.pathname === '/home'
    ? handleHomeBack
    : location.pathname === '/kassa' || location.pathname === '/kassa/nieuw'
      ? handleKassaBack
      : null

  return (
    <div className="rz-mobile-app-chrome" data-testid="mobile-app-chrome">
      <MobileModuleHeader
        title={mobileRouteTitle(location.pathname)}
        className="rz-mobile-app-header"
        testId={isSuperuserRoute ? 'mobile-superuser-header' : 'mobile-global-header'}
        showBack
        backTestId="mobile-global-back"
        onBack={backHandler}
      />
      {children}
      <div className="rz-mobile-app-bottom-space" aria-hidden="true" />
      <MobileBottomNavigationRuntime context={context} pathname={location.pathname} />
    </div>
  )
}
