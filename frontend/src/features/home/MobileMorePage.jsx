import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import {
  canCurrentUserPerform,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import { readHouseholdOnboarding } from '../onboarding/onboardingState.js'
import useFeatureAvailability from '../platform/useFeatureAvailability.js'
import { useActionButtonAvailability } from '../platform/actionButtonAvailability.js'
import { buildHomeNavigation } from './homeNavigation.js'
import {
  ACTION_ROUTE_BY_KEY,
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from './recentActionUsage.js'
import './mobileMore.css'

export default function MobileMorePage() {
  const navigate = useNavigate()
  const context = readStoredAuthContext()
  const features = useFeatureAvailability()
  const actionAvailability = useActionButtonAvailability({
    enabled: Boolean(context && context.context_type !== 'none'),
  })
  const onboarding = readHouseholdOnboarding(context)

  const tiles = useMemo(() => {
    const visibility = {
      canOpenAdmin: isHouseholdAdminFromContext(context),
      canOpenExternalDatabases: isFrontteamMemberFromContext(context),
      isPlatformSuperuser: isPlatformSuperuserFromContext(context),
      canOpenMessages: canCurrentUserPerform('platform.frontteam_messages.read', context),
      canManageLocations: canCurrentUserPerform('locations.manage', context),
    }
    const navigation = buildHomeNavigation({
      onboarding,
      visibility,
      features,
      actionButtons: actionAvailability.items,
      actionOrder: actionAvailability.order,
    })
    const seen = new Set()
    const available = [...navigation.primaryTiles, ...navigation.moreTiles]
      .filter((tile) => {
        const route = ACTION_ROUTE_BY_KEY[tile?.key]
        if (!tile?.clickable || !route || seen.has(tile.key)) return false
        seen.add(tile.key)
        return true
      })

    const currentBottom = selectRecentActionTiles({
      recentKeys: readRecentActionKeys(context),
      availableTiles: available,
      limit: 4,
    })
    const bottomKeys = new Set(currentBottom.map((tile) => tile.key))
    const remaining = available.filter((tile) => !bottomKeys.has(tile.key))
    return remaining.length ? remaining : available
  }, [
    context?.user_id,
    context?.context_type,
    actionAvailability.items,
    actionAvailability.order,
    features,
    onboarding,
  ])

  function open(tile) {
    const route = ACTION_ROUTE_BY_KEY[tile.key]
    if (!route) return
    recordRecentAction(tile.key, context)
    navigate(route)
  }

  return <main className="rz-mobile-more" data-testid="mobile-more-page">
    <MobileModuleHeader title="Meer" testId="mobile-more-header" />
    <section className="rz-mobile-more-inner">
      <h1>Andere hoofdfuncties</h1>
      <div className="rz-mobile-more-list">
        {tiles.map((tile) => (
          <button
            key={tile.key}
            type="button"
            onClick={() => open(tile)}
            data-testid={'mobile-more-' + tile.key}
          >
            <span>{tile.label}</span>
          </button>
        ))}
      </div>
    </section>
  </main>
}
